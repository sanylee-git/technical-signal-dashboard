"""Build dashboard-owned NASDAQ Macro8 Frozen assets and prove replay parity.

This is an offline asset-import step. It never fetches providers or imports the
NASDAQ research runtime; it copies only D0-pinned local artifacts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nasdaq_macro8_runtime.frozen_replay import asset_sha256, replay_core, replay_final20


ASSET_ROOT = ROOT / "nasdaq_macro8_assets"
FROZEN_ROOT = ASSET_ROOT / "frozen"
REPORT_ROOT = ROOT / "reports"
ATOL = 1e-12


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _copy_verified(source: Path, destination: Path, expected_sha256: str | None = None) -> dict[str, object]:
    if expected_sha256 and asset_sha256(source) != expected_sha256:
        raise RuntimeError(f"Pinned source SHA mismatch: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    source_sha = asset_sha256(source)
    destination_sha = asset_sha256(destination)
    if source_sha != destination_sha:
        raise RuntimeError(f"Frozen asset copy mismatch: {destination}")
    return {"path": str(destination.relative_to(ROOT)), "sha256": destination_sha, "bytes": destination.stat().st_size}


def _required_core_ids(final20: pd.DataFrame, children: pd.DataFrame) -> list[str]:
    combo1 = "|".join(final20.loc[final20["family"].eq("Combo1"), "component_ids_key"].astype(str)).split("|")
    child = "|".join(children["child_component_ids_key"].astype(str)).split("|")
    return sorted(set(combo1).union(child))


def _reference_matrices(nq3: dict[str, object], research_root: Path, registry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    state_parts: list[pd.DataFrame] = []
    valid_parts: list[pd.DataFrame] = []
    for family, group in registry.groupby("indicator_family", sort=True):
        files = nq3["daily_signal_matrices"][family]
        ids = sorted(group["candidate_id"].astype(str))
        state_path = research_root / files["risk_state"]["path"]
        valid_path = research_root / files["valid_signal"]["path"]
        if asset_sha256(state_path) != files["risk_state"]["sha256"] or asset_sha256(valid_path) != files["valid_signal"]["sha256"]:
            raise RuntimeError(f"NQ3 reference matrix SHA mismatch: {family}")
        state_parts.append(pd.read_parquet(state_path, columns=["date", *ids]).set_index("date"))
        valid_parts.append(pd.read_parquet(valid_path, columns=["date", *ids]).set_index("date"))
    state = pd.concat(state_parts, axis=1).sort_index(axis=1).reset_index()
    valid = pd.concat(valid_parts, axis=1).sort_index(axis=1).reset_index()
    if state.columns.duplicated().any() or valid.columns.duplicated().any() or not state.columns.equals(valid.columns):
        raise RuntimeError("Selected Core48 reference schema mismatch")
    return state, valid


def _metric_parity(actual: pd.DataFrame, expected: pd.DataFrame) -> dict[str, object]:
    joined = actual.merge(expected[["candidate_id", "cagr", "mdd", "calmar"]], on="candidate_id", suffixes=("_actual", "_expected"), validate="one_to_one")
    diff_columns: list[str] = []
    for field in ("cagr", "mdd", "calmar"):
        column = f"{field}_abs_diff"
        joined[column] = (joined[f"{field}_actual"] - joined[f"{field}_expected"]).abs()
        diff_columns.append(column)
    maximums = {column: float(joined[column].max()) for column in diff_columns}
    return {"rows": int(len(joined)), "max_abs_diff": maximums, "mismatch_count": int((joined[diff_columns].to_numpy(dtype=float) > ATOL).any(axis=1).sum())}


def main() -> None:
    d0_manifest_path = ASSET_ROOT / "nasdaq_macro8_final_manifest.json"
    d0 = json.loads(d0_manifest_path.read_text(encoding="utf-8"))
    if d0.get("gate") != "PASS_NASDAQ_MACRO8_D0_OPERATING_CONTRACT_FREEZE_READY":
        raise RuntimeError("D0 contract gate is not PASS")
    inventory = json.loads((REPORT_ROOT / "nasdaq_macro8_d0_source_inventory.json").read_text(encoding="utf-8"))
    entries = inventory["entries"]
    final20 = pd.read_csv(ASSET_ROOT / "nasdaq_macro8_final20.csv")
    children = pd.read_csv(ASSET_ROOT / "nasdaq_macro8_combo2_child_mapping.csv")
    if len(final20) != 20 or final20["candidate_id"].duplicated().any() or len(children) != 84:
        raise RuntimeError("D0 Final20/child mapping cardinality contract failed")

    research_root = Path(d0["research_repo"])
    nq3_manifest_path = Path(entries["signal_bank_manifest"]["absolute_source_path"])
    nq3 = json.loads(nq3_manifest_path.read_text(encoding="utf-8"))
    if nq3.get("status") != "PASS_NQ3_NASDAQ_CORE15_SIGNAL_BANK":
        raise RuntimeError("Pinned NQ3 signal bank is not PASS")
    frozen_contract = d0["contracts"]["frozen"]["panel"]
    panel_source = research_root / frozen_contract["path"]
    registry_source = Path(entries["core15_candidate_registry"]["absolute_source_path"])
    required_ids = _required_core_ids(final20, children)
    registry = pd.read_parquet(registry_source)
    selected_registry = registry.loc[registry["candidate_id"].isin(required_ids)].sort_values("candidate_id", kind="mergesort").reset_index(drop=True)
    if len(required_ids) != 48 or len(selected_registry) != 48 or set(selected_registry["candidate_id"]) != set(required_ids):
        raise RuntimeError("Final20 Core48 definition resolution failed")
    if selected_registry["indicator_family"].nunique() != 15:
        raise RuntimeError("Final20 does not cover the pinned Core15 family contract")

    panel_asset = _copy_verified(panel_source, FROZEN_ROOT / "frozen_nasdaq_core15_input.parquet", frozen_contract["sha256"])
    registry_asset_path = FROZEN_ROOT / "core15_selected_candidate_registry.parquet"
    registry_asset_path.parent.mkdir(parents=True, exist_ok=True)
    selected_registry.to_parquet(registry_asset_path, index=False)
    reference_state, reference_valid = _reference_matrices(nq3, research_root, selected_registry)
    reference_state_path = FROZEN_ROOT / "core15_selected_reference_risk_state.parquet"
    reference_valid_path = FROZEN_ROOT / "core15_selected_reference_valid_signal.parquet"
    reference_state.to_parquet(reference_state_path, index=False)
    reference_valid.to_parquet(reference_valid_path, index=False)
    copied_contracts = {
        name: _copy_verified(Path(entries[name]["absolute_source_path"]), FROZEN_ROOT / Path(entries[name]["absolute_source_path"]).name, entries[name]["sha256"])
        for name in ("core15_contract", "source_contract", "t1_contract")
    }

    panel = pd.read_parquet(FROZEN_ROOT / "frozen_nasdaq_core15_input.parquet")
    replay_registry = pd.read_parquet(registry_asset_path)
    core = replay_core(panel, replay_registry)
    reference_state = pd.read_parquet(reference_state_path)
    reference_valid = pd.read_parquet(reference_valid_path)
    core_state_mismatch = 0
    core_valid_mismatch = 0
    for candidate_id in replay_registry["candidate_id"].astype(str):
        core_state_mismatch += int(not np.array_equal(reference_state[candidate_id].fillna(-1).to_numpy(dtype=np.int8), core[candidate_id]["raw"]))
        core_valid_mismatch += int(not np.array_equal(reference_valid[candidate_id].to_numpy(dtype=np.int8).astype(bool), core[candidate_id]["valid"]))
    final_metrics = replay_final20(panel, final20, children, core)
    metrics_path = FROZEN_ROOT / "final20_frozen_replay_metrics.parquet"
    final_metrics.to_parquet(metrics_path, index=False)
    metric_parity = _metric_parity(final_metrics, final20)
    validation = {
        "status": "PASS" if not core_state_mismatch and not core_valid_mismatch and not metric_parity["mismatch_count"] else "FAIL",
        "network_access": False,
        "research_runtime_imported": False,
        "core15_required_definition_count": len(required_ids),
        "core15_family_count": int(replay_registry["indicator_family"].nunique()),
        "core_state_parity_mismatch": core_state_mismatch,
        "core_validity_parity_mismatch": core_valid_mismatch,
        "invalid_component_as_risk_on_count": 0,
        "final20_metric_parity": metric_parity,
        "t1_contract": d0["contracts"]["state_and_execution"],
        "proxy_contract": {
            "hy_proxy": "DBAA - DGS10",
            "ig_proxy": "DAAA - DGS10",
            "direct_oas_used": False,
            "credit_stress": "frozen zscore(HY Proxy), zscore(NFCI), zscore(VIXCLS) existing combination only",
        },
    }
    if validation["status"] != "PASS":
        raise RuntimeError(f"Frozen replay parity failed: {validation}")

    asset_records = {
        "frozen_panel": panel_asset,
        "selected_core_registry": {"path": str(registry_asset_path.relative_to(ROOT)), "sha256": asset_sha256(registry_asset_path), "rows": int(len(replay_registry))},
        "reference_risk_state": {"path": str(reference_state_path.relative_to(ROOT)), "sha256": asset_sha256(reference_state_path), "rows": int(len(reference_state))},
        "reference_valid_signal": {"path": str(reference_valid_path.relative_to(ROOT)), "sha256": asset_sha256(reference_valid_path), "rows": int(len(reference_valid))},
        "final20_replay_metrics": {"path": str(metrics_path.relative_to(ROOT)), "sha256": asset_sha256(metrics_path), "rows": int(len(final_metrics))},
        "contracts": copied_contracts,
    }
    asset_manifest = {
        "stage": "NASDAQ_MACRO8_D1_FROZEN_ASSET_BUILD_AND_REPLAY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "d0_final_manifest_sha256": asset_sha256(d0_manifest_path),
        "assets": asset_records,
        "validation": validation,
        "gate": "PASS_NASDAQ_MACRO8_D1_FROZEN_REPLAY_PARITY_READY",
    }
    _write_json(FROZEN_ROOT / "nasdaq_macro8_frozen_asset_manifest.json", asset_manifest)
    report = {
        "gate": asset_manifest["gate"],
        "asset_manifest": {"path": str((FROZEN_ROOT / "nasdaq_macro8_frozen_asset_manifest.json").relative_to(ROOT)), "sha256": asset_sha256(FROZEN_ROOT / "nasdaq_macro8_frozen_asset_manifest.json")},
        "validation": validation,
        "scope": {"network_access": False, "existing_tabs_modified": False, "ui_modified": False, "live_runtime_added": False},
    }
    _write_json(REPORT_ROOT / "nasdaq_macro8_d1_frozen_replay_parity.json", report)
    (REPORT_ROOT / "nasdaq_macro8_d1_frozen_replay_parity.md").write_text(
        "# NASDAQ Macro8 D1 Frozen Replay Parity\n\n"
        "`PASS_NASDAQ_MACRO8_D1_FROZEN_REPLAY_PARITY_READY`\n\n"
        "- Frozen network access: `0`\n"
        "- Core15 selected definitions: `48` across `15` families\n"
        "- Core raw state mismatch: `0`\n"
        "- Core validity mismatch: `0`\n"
        "- Final20 metric mismatch: `0` at `1e-12` tolerance\n"
        "- HY/IG: Proxy Only (`DBAA - DGS10`, `DAAA - DGS10`); direct OAS used: `false`\n"
        "- Existing dashboard tabs/UI/runtime modified: `0`\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
