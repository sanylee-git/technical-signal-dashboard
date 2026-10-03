"""S&P2 selected 5+5 runtime using the corrected Single69 bank."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import asset_sha256
from .live_replay import (
    performance_calendar,
    replay_combo1_raw_history,
    replay_core,
    replay_final10,
    replay_final10_history,
)
from .live_runtime import _snapshot, run_live_runtime


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "spx_macro9_assets" / "selected_final20"
OUTPUTS = (
    "snp_source_panel.parquet",
    "snp_single69_registry.parquet",
    "single_raw_state.parquet",
    "single_raw_valid.parquet",
    "final_candidates.csv",
    "combo2_child_mapping.csv",
)


def _read_frozen_inputs() -> tuple[
    dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame,
    pd.DataFrame, pd.DataFrame, pd.DataFrame,
]:
    manifest_path = ASSETS / "selected_final20_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_SNP2_SELECTED_FINAL10_ASSETS_READY":
        raise RuntimeError("S&P2 selected Final10 asset gate is not PASS")
    if manifest.get("contract") != "snp2_selected_final10_v1":
        raise RuntimeError("S&P2 selected Final10 contract mismatch")
    for name in OUTPUTS:
        path = ASSETS / name
        pin = manifest.get("outputs", {}).get(name, {})
        if not path.is_file() or asset_sha256(path) != pin.get("sha256"):
            raise RuntimeError(f"S&P2 selected Final10 asset SHA mismatch: {name}")

    panel = pd.read_parquet(ASSETS / "snp_source_panel.parquet")
    registry = pd.read_parquet(ASSETS / "snp_single69_registry.parquet")
    raw_reference = pd.read_parquet(ASSETS / "single_raw_state.parquet")
    valid_reference = pd.read_parquet(ASSETS / "single_raw_valid.parquet")
    final = pd.read_csv(ASSETS / "final_candidates.csv", keep_default_na=False)
    children = pd.read_csv(ASSETS / "combo2_child_mapping.csv", keep_default_na=False)

    for frame in (panel, raw_reference, valid_reference):
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    panel = panel.sort_values("date", kind="mergesort").reset_index(drop=True)
    raw_reference = raw_reference.sort_values("date", kind="mergesort").reset_index(drop=True)
    valid_reference = valid_reference.sort_values("date", kind="mergesort").reset_index(drop=True)
    if panel.date.duplicated().any() or not panel.date.is_monotonic_increasing:
        raise RuntimeError("S&P2 selected source panel calendar is not unique/sorted")
    if not panel.date.equals(raw_reference.date) or not panel.date.equals(valid_reference.date):
        raise RuntimeError("S&P2 selected Single69 calendars do not match the source panel")
    if len(registry) != 69 or not registry.candidate_id.astype(str).is_unique:
        raise RuntimeError("S&P2 selected Single69 registry count/identity mismatch")
    component_ids = set(registry.candidate_id.astype(str))
    if set(raw_reference.columns.drop("date").astype(str)) != component_ids:
        raise RuntimeError("S&P2 selected Single69 raw reference schema mismatch")
    if set(valid_reference.columns.drop("date").astype(str)) != component_ids:
        raise RuntimeError("S&P2 selected Single69 validity reference schema mismatch")

    counts = final.groupby("family").size().to_dict()
    expected_ids = manifest.get("candidate_ids", {})
    if counts != {"Combo1": 5, "Combo2": 5} or len(final) != 10:
        raise RuntimeError("S&P2 selected Final10 candidate-count contract mismatch")
    if final.candidate_id.astype(str).duplicated().any():
        raise RuntimeError("S&P2 selected Final10 has duplicate candidate IDs")
    for family in ("Combo1", "Combo2"):
        actual = final.loc[final.family.eq(family)].sort_values("display_order").candidate_id.astype(str).tolist()
        if actual != expected_ids.get(family):
            raise RuntimeError(f"S&P2 selected Final10 {family} frozen ID/order mismatch")
    expected_main_ids = {
        "Combo1": {
            "Main1": "da862ec08d016b6f056c71d4",
            "Main2": "e4ad56aa66de8a3f2fb7c645",
        },
        "Combo2": {
            "Main1": "6b4595522bbed808d41be978",
            "Main2": "c9d4c64e586e2e9f8fb2cff1",
        },
    }
    if manifest.get("main_candidate_ids") != expected_main_ids:
        raise RuntimeError("S&P2 selected Main1/Main2 candidate contract mismatch")
    for family, slots in expected_main_ids.items():
        family_rows = final.loc[final.family.eq(family)]
        for slot, candidate_id in slots.items():
            main = family_rows.loc[family_rows.candidate_id.eq(candidate_id)]
            if len(main) != 1 or not str(main.iloc[0].display_role).startswith(slot):
                raise RuntimeError(f"S&P2 selected {family} {slot} display contract mismatch")
        ordered_ids = family_rows.sort_values("display_order").candidate_id.astype(str).tolist()
        if ordered_ids[:2] != [slots["Main1"], slots["Main2"]]:
            raise RuntimeError(f"S&P2 selected {family} main display order mismatch")
    if manifest.get("default_candidate_id") != expected_main_ids["Combo2"]["Main1"]:
        raise RuntimeError("S&P2 selected default candidate must be Combo2 Main1")

    for row in final.itertuples(index=False):
        members = str(row.component_ids_key).split("|")
        if row.family == "Combo1" and (len(members) != int(row.n_or_m) or not set(members).issubset(component_ids)):
            raise RuntimeError(f"S&P2 selected Combo1 component lineage mismatch: {row.candidate_id}")
        if row.family == "Combo2" and len(members) != int(row.n_or_m):
            raise RuntimeError(f"S&P2 selected Combo2 child count mismatch: {row.candidate_id}")
    for parent_id, group in children.groupby("parent_candidate_id", sort=False):
        model = final.loc[final.candidate_id.eq(parent_id)]
        if len(model) != 1 or model.iloc[0].family != "Combo2":
            raise RuntimeError(f"S&P2 selected Combo2 mapping has an unknown parent: {parent_id}")
        ordered = group.sort_values("child_order", kind="mergesort").child_canonical_parent_id.astype(str).tolist()
        if ordered != str(model.iloc[0].component_ids_key).split("|"):
            raise RuntimeError(f"S&P2 selected Combo2 child order mismatch: {parent_id}")
        for child in group.itertuples(index=False):
            members = str(child.child_component_ids_key).split("|")
            if len(members) != int(child.child_n) or not set(members).issubset(component_ids):
                raise RuntimeError(f"S&P2 selected Combo2 child component lineage mismatch: {child.child_canonical_parent_id}")

    dates, _mask, start, end, _returns = performance_calendar(panel)
    period = manifest.get("evaluation_period", {})
    if (
        end - start + 1 != int(period.get("trading_sessions", -1))
        or dates[start].strftime("%Y-%m-%d") != period.get("start")
        or dates[end].strftime("%Y-%m-%d") != period.get("end")
    ):
        raise RuntimeError("S&P2 selected Final10 evaluation calendar contract mismatch")
    return manifest, panel, registry, raw_reference, valid_reference, final, children


def _frozen_runtime() -> dict[str, Any]:
    manifest, panel, registry, raw_reference, valid_reference, final, children = _read_frozen_inputs()
    core = replay_core(panel, registry, force_previous_threshold=True)
    raw_mismatch = 0
    valid_mismatch = 0
    for candidate_id in registry.candidate_id.astype(str):
        expected_raw = pd.to_numeric(raw_reference[candidate_id], errors="coerce").fillna(-1).to_numpy(dtype=np.int8)
        expected_valid = valid_reference[candidate_id].to_numpy(dtype=bool)
        raw_mismatch += int(np.count_nonzero(core[candidate_id]["raw"] != expected_raw))
        valid_mismatch += int(np.count_nonzero(core[candidate_id]["valid"] != expected_valid))
    if raw_mismatch or valid_mismatch:
        raise RuntimeError(f"S&P2 corrected Single69 parity failed: raw={raw_mismatch}, valid={valid_mismatch}")

    metrics = replay_final10(panel, final, children, core)
    history = replay_final10_history(panel, final, children, core)
    reference = final.set_index("candidate_id")
    for row in metrics.itertuples(index=False):
        expected = reference.loc[str(row.candidate_id)]
        if row.state_hash != str(expected.official_t1_state_sha256):
            raise RuntimeError(f"S&P2 selected official T+1 reference mismatch: {row.candidate_id}")
        if not np.isclose(float(row.cagr), float(expected.cagr), rtol=0.0, atol=1e-8):
            raise RuntimeError(f"S&P2 selected CAGR reference mismatch: {row.candidate_id}")
        if not np.isclose(float(row.mdd), float(expected.mdd), rtol=0.0, atol=1e-8):
            raise RuntimeError(f"S&P2 selected MDD reference mismatch: {row.candidate_id}")

    child_history = replay_combo1_raw_history(panel, children, core)
    latest = history.sort_values("date", kind="mergesort").groupby("candidate_id", sort=False).tail(1).set_index("candidate_id")
    child_latest = child_history.sort_values("date", kind="mergesort").groupby("combo1_id", sort=False).tail(1).set_index("combo1_id")
    seeds = {
        "c1_raw": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "strategy_risk_state"]) for row in final.loc[final.family.eq("Combo1")].itertuples(index=False)},
        "c1_active": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "active_count"]) for row in final.loc[final.family.eq("Combo1")].itertuples(index=False)},
        "c2_raw": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "strategy_risk_state"]) for row in final.loc[final.family.eq("Combo2")].itertuples(index=False)},
        "c2_active": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "active_count"]) for row in final.loc[final.family.eq("Combo2")].itertuples(index=False)},
        "child_raw": {str(index): int(row["raw_risk_state"]) for index, row in child_latest.iterrows()},
    }
    return {
        "runtime_mode": "FROZEN_ONLY",
        "network_access": False,
        "basis_date": str(manifest["evaluation_period"]["end"]),
        "frozen_cutoff": str(manifest["evaluation_period"]["end"]),
        "proxy_only": True,
        "direct_oas_used": False,
        "snapshot": _snapshot(final, history, panel, status="FROZEN_ONLY"),
        "metrics": metrics,
        "history": history,
        "panel": panel,
        "registry": registry,
        "final10": final,
        "children": children,
        "seeds": seeds,
        "core": core,
        "selected_asset_manifest_sha256": asset_sha256(ASSETS / "selected_final20_manifest.json"),
        "single69_raw_mismatch": raw_mismatch,
        "single69_valid_mismatch": valid_mismatch,
        "official_t1_application_count": 1,
    }


def run_selected_final20_runtime(*, as_of: object = None, provider_frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    """Use the selected frozen 5+5 source, then append the standard live tail."""
    return run_live_runtime(
        as_of=as_of,
        provider_frames=provider_frames,
        frozen_runtime=_frozen_runtime(),
        force_previous_threshold=True,
    )
