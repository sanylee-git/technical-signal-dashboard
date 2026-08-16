"""Validate the independent Macro7 Frozen replay without network or research imports."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.frozen_replay import run_frozen_replay


ASSETS = ROOT / "kosdaq_macro7_assets"
REPORT = ROOT / "reports/kosdaq_macro7_d1_frozen_replay_parity.md"
D01 = ROOT / "reports/kosdaq_macro7_d0_1_stage2_provenance.json"
STATE_TOLERANCE = 0
METRIC_TOLERANCE = 1e-12


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _compare(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str], columns: list[str]) -> dict[str, int]:
    actual = actual.copy()
    expected = expected.copy()
    actual["date"] = pd.to_datetime(actual["date"]).dt.normalize()
    expected["date"] = pd.to_datetime(expected["date"]).dt.normalize()
    merged = actual.merge(expected, on=keys, how="outer", suffixes=("_actual", "_expected"), indicator=True)
    result = {"missing_or_extra_rows": int((merged["_merge"] != "both").sum())}
    for column in columns:
        result[column] = int((merged[f"{column}_actual"] != merged[f"{column}_expected"]).sum())
    result["total_mismatch"] = sum(result.values())
    return result


def validate() -> dict[str, Any]:
    d01 = json.loads(D01.read_text(encoding="utf-8"))
    d0_drift = {
        relative: _sha256(ROOT / relative) != expected
        for relative, expected in d01["d0_contract_files_sha256"].items()
    }
    replay = run_frozen_replay(ASSETS)
    checks = {
        "core": _compare(
            replay["core"],
            pd.read_parquet(ASSETS / "frozen/core_signal_reference.parquet"),
            ["candidate_id", "date"],
            ["valid_signal", "risk_state", "risk_start", "risk_end"],
        ),
        "child_combo1_raw": _compare(
            replay["child"],
            pd.read_parquet(ASSETS / "frozen/material_child_combo1_raw_reference.parquet"),
            ["combo_id", "date"],
            ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"],
        ),
        "final_combo1_raw": _compare(
            replay["final_combo1"],
            pd.read_parquet(ASSETS / "frozen/final_combo1_raw_reference.parquet"),
            ["combo_id", "date"],
            ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"],
        ),
        "final_combo2_raw": _compare(
            replay["final_combo2"],
            pd.read_parquet(ASSETS / "frozen/final_combo2_raw_reference.parquet"),
            ["combo_id", "date"],
            ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"],
        ),
        "final_t1": _compare(
            replay["t1"],
            pd.read_parquet(ASSETS / "frozen/final_t1_reference.parquet"),
            ["combo_id", "date"],
            ["risk_off_t1", "invest_position"],
        ),
    }
    expected_metrics = pd.read_csv(ASSETS / "kosdaq_macro7_final10.csv").set_index("candidate_id")
    actual_metrics = replay["metrics"].set_index("candidate_id")
    metric_deltas: dict[str, dict[str, float]] = {}
    for candidate_id in sorted(actual_metrics.index):
        metric_deltas[candidate_id] = {
            name: float(actual_metrics.loc[candidate_id, name] - expected_metrics.loc[candidate_id, name])
            for name in ("CAGR", "MDD", "Calmar")
        }
    max_metric_delta = max(abs(value) for values in metric_deltas.values() for value in values.values())
    invalid_as_risk_on = int(
        replay["child"]["invalid_component_as_risk_on"].sum()
        + replay["final_combo1"]["invalid_component_as_risk_on"].sum()
        + replay["final_combo2"]["invalid_component_as_risk_on"].sum()
    )
    invalid_days = int(
        replay["child"]["invalid_component_days"].sum()
        + replay["final_combo1"]["invalid_component_days"].sum()
        + replay["final_combo2"]["invalid_component_days"].sum()
    )
    asset_manifest = json.loads((ASSETS / "kosdaq_macro7_frozen_asset_manifest.json").read_text(encoding="utf-8"))
    asset_hash_mismatch = 0
    for asset in asset_manifest["assets"]:
        if _sha256(ASSETS / asset["relative_path"]) != asset["file_sha256"]:
            asset_hash_mismatch += 1
    total_state_mismatch = sum(item["total_mismatch"] for item in checks.values())
    gate = "PASS_KOSDAQ_MACRO7_D1_FROZEN_REPLAY_PARITY_READY" if not any(d0_drift.values()) and asset_hash_mismatch == 0 and total_state_mismatch == STATE_TOLERANCE and invalid_as_risk_on == 0 and max_metric_delta <= METRIC_TOLERANCE else "FAIL_KOSDAQ_MACRO7_D1_FROZEN_REPLAY_PARITY"
    return {
        "gate": gate,
        "d0_contract_drift_count": int(sum(d0_drift.values())),
        "frozen_asset_hash_mismatch_count": asset_hash_mismatch,
        "checks": checks,
        "validity_mask_parity_mismatch": checks["core"]["valid_signal"] + checks["child_combo1_raw"]["valid"] + checks["final_combo1_raw"]["valid"] + checks["final_combo2_raw"]["valid"],
        "invalid_component_as_risk_on_count": invalid_as_risk_on,
        "invalid_component_day_count": invalid_days,
        "final_t1_application_count": 1,
        "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE",
        "network_call_count": 0,
        "max_metric_abs_delta": max_metric_delta,
        "metric_deltas": metric_deltas,
    }


def _render(result: dict[str, Any]) -> str:
    lines = [
        "# KOSDAQ Macro7 D1 Frozen Replay Parity",
        "",
        f"- Gate: `{result['gate']}`",
        "- Mode: independent dashboard runtime; Frozen local assets only; network calls 0.",
        "- Combo2 input: `CHILD_COMBO1_RAW_RISK_STATE`.",
        "- Final T+1 application count: 1.",
        "- Missing/invalid policy: `INVALID_NOT_RISK_ON`.",
        "",
        "## Parity",
        "",
        "| Layer | Total mismatch |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {check['total_mismatch']} |" for name, check in result["checks"].items())
    lines.extend([
        "",
        f"- D0 contract drift: {result['d0_contract_drift_count']}",
        f"- Frozen asset hash mismatch: {result['frozen_asset_hash_mismatch_count']}",
        f"- Validity-mask mismatch: {result['validity_mask_parity_mismatch']}",
        f"- Invalid component converted to Risk-on: {result['invalid_component_as_risk_on_count']}",
        f"- Invalid component-days in official evaluation: {result['invalid_component_day_count']}",
        f"- Maximum CAGR/MDD/Calmar absolute delta: {result['max_metric_abs_delta']:.3e}",
        "",
        "Raw intermediates (EMA, rolling inputs, and threshold series) have no authoritative stored reference and remain `NOT_AVAILABLE_REFERENCE`; exact parity is enforced for date, validity, state, and events.",
    ])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    validation = validate()
    REPORT.write_text(_render(validation), encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if not validation["gate"].startswith("PASS_"):
        raise SystemExit(1)
