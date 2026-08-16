"""Validate Macro7 Live runtime boundaries without altering Frozen artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_runtime import FROZEN_CUTOFF, run_live_runtime


ASSETS = ROOT / "kosdaq_macro7_assets"
REPORT = ROOT / "reports/kosdaq_macro7_d2_live_runtime_validation.md"
IMMUTABLE = {
    "kosdaq_macro7_assets/kosdaq_macro7_final10.csv": "2048053e07be73fb76b6a8a6ee4b8ba0fe070ab13b52f66f4185db717c454551",
    "kosdaq_macro7_assets/kosdaq_macro7_combo2_child_mapping.csv": "0ab2fe1e202bad7014fe2c263dc0c60fc3247972511df95f446e2fafa2e7e5d3",
    "kosdaq_macro7_assets/kosdaq_macro7_final_manifest.json": "7353c92265f65012eb7e0f3c56b2503724ccd78a77d99203529728d3a690bf96",
    "reports/kosdaq_macro7_d0_source_inventory.json": "9d4afc96a06c1c2df5675ea0eacf632b627c7af7315822c324efafc37be1e152",
    "reports/kosdaq_macro7_d0_contract_freeze.md": "69b231a19a0f9f068b692d27a31e93c161fd245cd1e948340742771a395a335f",
    "reports/kosdaq_macro7_d0_1_stage2_provenance.json": "4a42e49a52ca1741693c7c4c99552fae7086b3429ee36a3f59bda8ef9a6e12c7",
    "kosdaq_macro7_runtime/frozen_replay.py": "d25a48342ffd0b4bfebb0af96b0203a96b69d39cb4b335b709db6d4ccd03465b",
    "kosdaq_macro7_runtime/__init__.py": "4932d7ab6cbc84f924cc9ac65a94c36dbe6058a768812b0d0497ed23c02521d1",
    "kosdaq_macro7_assets/kosdaq_macro7_signal_definitions.csv": "eed8725834e61e56b966bac5327542f7b332d1d441a8fadd6b4d99221e2bccac",
    "kosdaq_macro7_assets/kosdaq_macro7_frozen_asset_manifest.json": "1f8db9dacb57d31744832964f86a86487892d8d692577c6cfb7c8adf86a1f10c",
    "reports/kosdaq_macro7_d1_frozen_replay_parity.md": "d2528f561a52f89e9d6ca2c0fc61384922f22329529e5ce142923babbccebba8",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prefix_mismatch(actual: pd.DataFrame, reference_path: Path, keys: list[str], columns: list[str]) -> int:
    expected = pd.read_parquet(reference_path)
    actual = actual.copy()
    for frame in (actual, expected):
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    actual = actual.loc[actual["date"].le(FROZEN_CUTOFF)]
    expected = expected.loc[expected["date"].le(FROZEN_CUTOFF)]
    merged = actual.merge(expected, on=keys, how="outer", suffixes=("_actual", "_expected"), indicator=True)
    return int((merged["_merge"] != "both").sum()) + sum(int((merged[f"{column}_actual"] != merged[f"{column}_expected"]).sum()) for column in columns)


def _boundary_checks(result: dict[str, Any]) -> dict[str, int]:
    """Verify the Frozen-to-live state handoff instead of inferring it from a summary."""
    state_reset_count = 0
    t1_reset_count = 0
    final_frames = [result["final_combo1"], result["final_combo2"]]
    for frame in final_frames:
        if frame.empty:
            continue
        cutoff_rows = frame.loc[pd.to_datetime(frame["date"]).eq(FROZEN_CUTOFF)]
        state_reset_count += int(cutoff_rows["raw_risk_state"].isna().sum())

    t1 = result["t1"].copy()
    if not t1.empty:
        t1["date"] = pd.to_datetime(t1["date"]).dt.normalize()
        for _, group in t1.groupby("combo_id", sort=True):
            group = group.sort_values("date")
            first_live = group.loc[group["date"].gt(FROZEN_CUTOFF)].head(1)
            if first_live.empty:
                continue
            previous = group.loc[group["date"].lt(first_live.iloc[0]["date"])].tail(1)
            if previous.empty or bool(first_live.iloc[0]["risk_off_t1"]) != bool(previous.iloc[0]["raw_risk_state"]):
                t1_reset_count += 1
    return {
        "boundary_state_reset_count": state_reset_count,
        "boundary_t1_reset_count": t1_reset_count,
    }


def validate(*, live_result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = live_result or run_live_runtime()
    contract = json.loads((ASSETS / "kosdaq_macro7_live_source_contract.json").read_text(encoding="utf-8"))
    immutable_drift = [relative for relative, expected in IMMUTABLE.items() if _sha256(ROOT / relative) != expected]
    source_coverage = sorted({family for source in contract["sources"] for family in source["required_by_indicator_families"]})
    prefix = {
        "core": _prefix_mismatch(result["core"], ASSETS / "frozen/core_signal_reference.parquet", ["candidate_id", "date"], ["valid_signal", "risk_state", "risk_start", "risk_end"]),
        "child": _prefix_mismatch(result["child"], ASSETS / "frozen/material_child_combo1_raw_reference.parquet", ["combo_id", "date"], ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"]),
        "final_combo1": _prefix_mismatch(result["final_combo1"], ASSETS / "frozen/final_combo1_raw_reference.parquet", ["combo_id", "date"], ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"]),
        "final_combo2": _prefix_mismatch(result["final_combo2"], ASSETS / "frozen/final_combo2_raw_reference.parquet", ["combo_id", "date"], ["active_count", "valid", "raw_risk_state", "risk_start", "risk_end"]),
        "final_t1": _prefix_mismatch(result["t1"], ASSETS / "frozen/final_t1_reference.parquet", ["combo_id", "date"], ["risk_off_t1", "invest_position"]),
    }
    source_status = result["source_status"]
    boundary = _boundary_checks(result)
    freshness_bad = int((~source_status["freshness_status"].isin({"FRESH", "NO_NEW_RELEASE_EXPECTED", "EXPECTED_CADENCE_LAG"})).sum())
    snapshot = result["snapshot"]
    static_text = "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in ["kosdaq_macro7_runtime/live_sources.py", "kosdaq_macro7_runtime/market_calendar.py", "kosdaq_macro7_runtime/live_runtime.py"])
    forbidden = ["kospi_macro5_runtime", "kospi_macro5_assets", "macro_dashboard_kosdaq", "candidate_metadata.parquet", "outputs/kosdaq/run_"]
    isolation_hits = sum(token in static_text for token in forbidden)
    hard_pass = (
        not immutable_drift
        and len(source_coverage) == 15
        and result["merge"]["frozen_rows_overwritten"] == 0
        and result["merge"]["live_rows_on_or_before_cutoff_used_for_runtime"] == 0
        and result["merge"]["duplicate_date_count"] == 0
        and sum(prefix.values()) == 0
        and boundary["boundary_state_reset_count"] == 0
        and boundary["boundary_t1_reset_count"] == 0
        and result["invalid_component_as_risk_on_count"] == 0
        and result["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
        and result["final_t1_application_count"] == 1
        and isolation_hits == 0
        and int(snapshot["valid"].sum()) == 10
        and freshness_bad == 0
        and result["merge"]["live_tail_row_count"] > 0
    )
    return {
        "gate": "PASS_KOSDAQ_MACRO7_D2_LIVE_RUNTIME_READY" if hard_pass else "FAIL_KOSDAQ_MACRO7_D2_LIVE_RUNTIME",
        "immutable_drift": immutable_drift,
        "source_coverage_count": len(source_coverage),
        "source_coverage": source_coverage,
        "freshness_bad_count": freshness_bad,
        "prefix_mismatch": prefix,
        "boundary": boundary,
        "isolation_hits": isolation_hits,
        "merge": result["merge"],
        "market_session_status": result["market_session_status"],
        "provisional_intraday_model_state": result["provisional_intraday_model_state"],
        "source_status": source_status.to_dict(orient="records"),
        "snapshot": snapshot.to_dict(orient="records"),
        "combo2_input_semantics": result["combo2_input_semantics"],
        "final_t1_application_count": result["final_t1_application_count"],
        "invalid_component_as_risk_on_count": result["invalid_component_as_risk_on_count"],
    }


def _report(validation: dict[str, Any]) -> str:
    lines = ["# KOSDAQ Macro7 D2 Live Runtime Validation", "", f"- Gate: `{validation['gate']}`", "- Mode: independent KOSDAQ runtime; Frozen prefix remains authoritative.", f"- KRX session: `{validation['market_session_status']}`", f"- Provisional intraday model state: `{validation['provisional_intraday_model_state']}`", f"- Required family coverage: `{validation['source_coverage_count']}/15`", "", "## Boundary", "", *[f"- {key}: `{value}`" for key, value in validation["merge"].items()], "", "## Source Status", "", "| Source | Observation | Available Through | Freshness |", "|---|---|---|---|"]
    lines.extend(f"| {row['source_id']} | {row.get('observation_date') or '-'} | {row.get('available_through_date') or '-'} | {row.get('freshness_status')} |" for row in validation["source_status"])
    lines.extend(["", "## Final10 Snapshot", "", "| Candidate | Basis | Valid | Raw Risk-off |", "|---|---|---:|---:|"])
    lines.extend(f"| {row['candidate_id']} | {row.get('basis_date') or '-'} | {row.get('valid')} | {row.get('raw_risk_state', '-')} |" for row in validation["snapshot"])
    lines.extend(["", "## Contract Checks", "", f"- Frozen prefix mismatch: `{sum(validation['prefix_mismatch'].values())}`", f"- Boundary state reset: `{validation['boundary']['boundary_state_reset_count']}`", f"- Boundary T+1 reset: `{validation['boundary']['boundary_t1_reset_count']}`", f"- Invalid interpreted as Risk-on: `{validation['invalid_component_as_risk_on_count']}`", f"- Combo2 input: `{validation['combo2_input_semantics']}`", f"- Final T+1 application count: `{validation['final_t1_application_count']}`", f"- KOSPI/research runtime isolation hits: `{validation['isolation_hits']}`", f"- Immutable baseline drift: `{len(validation['immutable_drift'])}`", "", "A source observation date is retained as source metadata. Live model rows are KRX calculation trading dates; current segment returns end at each candidate basis date."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    outcome = validate()
    REPORT.write_text(_report(outcome), encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False, indent=2, default=str))
    if not outcome["gate"].startswith("PASS_"):
        raise SystemExit(1)
