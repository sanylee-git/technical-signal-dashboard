"""Validate Stage 3.1 presentation data without changing the Stage 3 runtime."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_runtime import run_live_runtime
from kosdaq_macro7_runtime.presentation_payload import build_presentation_payload
from kosdaq_macro7_runtime.operating_assets import load_operating_final_inputs
from dashboard_role_aware_market_stage import validate_market_metadata
from dashboard_role_aware_stage import classify_role_combo


ASSETS = ROOT / "kosdaq_macro7_assets"
REPORT = ROOT / "reports/kosdaq_macro7_d3_role_aware_operating_validation.md"
PRE_D2_1_IMMUTABLE = {
    "kosdaq_macro7_assets/kosdaq_macro7_final10.csv": "2048053e07be73fb76b6a8a6ee4b8ba0fe070ab13b52f66f4185db717c454551",
    "kosdaq_macro7_assets/kosdaq_macro7_combo2_child_mapping.csv": "0ab2fe1e202bad7014fe2c263dc0c60fc3247972511df95f446e2fafa2e7e5d3",
    "kosdaq_macro7_assets/kosdaq_macro7_final_manifest.json": "7353c92265f65012eb7e0f3c56b2503724ccd78a77d99203529728d3a690bf96",
    "kosdaq_macro7_assets/kosdaq_macro7_signal_definitions.csv": "eed8725834e61e56b966bac5327542f7b332d1d441a8fadd6b4d99221e2bccac",
    "kosdaq_macro7_assets/kosdaq_macro7_frozen_asset_manifest.json": "1f8db9dacb57d31744832964f86a86487892d8d692577c6cfb7c8adf86a1f10c",
    "kosdaq_macro7_assets/kosdaq_macro7_live_source_contract.json": "e034436082061b7f35c56d6ddf8ded175fcc12a6f7ef6cfd2a4c0f25269ead81",
    "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_asset.parquet": "44e485bbb85c1507281df2febadeaa3e9179d278bbc98b9da52e8ab277c810f7",
    "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_contract.json": "d24c05fa6a29fc5dc9b54d1b4dd0ebbcaa64cfe182b3d09dbd15ffa5ea2122d4",
    "kosdaq_macro7_runtime/frozen_replay.py": "d25a48342ffd0b4bfebb0af96b0203a96b69d39cb4b335b709db6d4ccd03465b",
    "kosdaq_macro7_runtime/live_runtime.py": "56d7b31407f700d2418e5dd41d4af1f9db4c67777ff94470301f37d4386b352f",
    "kosdaq_macro7_runtime/live_sources.py": "d137cd3993b7eba758f3c4f24ef9e785e69c84cdc728174a6789b4cc41164d24",
    "kosdaq_macro7_runtime/market_calendar.py": "9f0d1f7777165f4ef23de427823e02290826f1e02bc824d344bc15b64c5ce694",
    "tools/kosdaq_macro7_validate_live_runtime.py": "9188279db30d038fc229b1a9c9e5edd825136da615cfcbe62fb770828ee14f89",
    "tests/test_kosdaq_macro7_d2_live_runtime.py": "be9763a7dccea42a9d74852f7c0651f060ab25a53a95043986ce3a34b65af679",
    "reports/kosdaq_macro7_d2_live_runtime_validation.md": "17b45da3789a82ad0c2db779ded7f867e739e0a2cacf52f3ab7dcadd6a26977b",
}
FROZEN_IMMUTABLE = {path: digest for path, digest in PRE_D2_1_IMMUTABLE.items() if path.startswith("kosdaq_macro7_assets/")}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _after_basis(frame: pd.DataFrame, key: str, bases: dict[str, pd.Timestamp]) -> int:
    if frame.empty:
        return 0
    dated = frame.copy()
    dated["date"] = pd.to_datetime(dated["date"]).dt.normalize()
    count = 0
    for value, group in dated.groupby(key, sort=False):
        basis = bases.get(str(value))
        if basis is not None:
            count += int(group["date"].gt(basis).sum())
    return count


def validate(*, live_payload: dict[str, Any] | None = None, presentation_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    live = live_payload or run_live_runtime()
    payload = presentation_payload or build_presentation_payload(live)
    frozen_drift = [path for path, expected in FROZEN_IMMUTABLE.items() if _sha256(ROOT / path) != expected]
    operating_manifest = json.loads((ASSETS / "operating/kosdaq_macro7_operating_manifest.json").read_text(encoding="utf-8"))
    role_metadata = json.loads((ASSETS / "operating/kosdaq_macro7_role_metadata.json").read_text(encoding="utf-8"))
    operating_final, _definitions, _children = load_operating_final_inputs()
    operating_file_drift = [
        name for name, expected in operating_manifest["operating_files"].items()
        if _sha256(ASSETS / "operating" / name) != expected
    ]
    final = payload["final10"].sort_values(["model_family", "display_slot"])
    snapshot = payload["snapshot"]
    bases = {
        str(row.candidate_id): pd.Timestamp(row.basis_date)
        for row in snapshot.itertuples(index=False)
        if getattr(row, "basis_date", None)
    }
    chart_parity = int((~payload["component_chart_history"]["risk_state_parity"].fillna(False).astype(bool)).sum())
    candidate_after_basis = _after_basis(payload["candidate_history"], "candidate_id", bases)
    component_after_basis = _after_basis(payload["component_history"], "parent_candidate_id", bases)
    benchmark_after_basis = _after_basis(payload["benchmark_history"], "candidate_id", bases)
    full = payload["frozen_display_metrics"].loc[payload["frozen_display_metrics"]["window"].eq("FULL")]
    metrics = final[["candidate_id", "CAGR", "MDD"]].merge(full[["candidate_id", "cagr", "mdd"]], on="candidate_id", how="left")
    metric_delta = max(
        float((metrics["CAGR"] - metrics["cagr"]).abs().max()),
        float((metrics["MDD"] - metrics["mdd"]).abs().max()),
    )
    unavailable = snapshot[~snapshot["valid"].fillna(False).astype(bool)]
    unavailable_as_risk_on = int(unavailable["raw_risk_state"].fillna(False).astype(bool).eq(False).sum()) if not unavailable.empty else 0
    source = (ROOT / "kosdaq_macro7_runtime/presentation_payload.py").read_text(encoding="utf-8")
    forbidden = ["streamlit", "requests", "yfinance", "st.cache", "fetch_all_sources", "kospi_macro5_runtime", "kospi_macro5_assets", "macro_dashboard_kosdaq"]
    forbidden_hits = [token for token in forbidden if token in source]
    final_order = snapshot["candidate_id"].astype(str).tolist()
    expected_order = final["candidate_id"].astype(str).tolist()
    role_validation = validate_market_metadata("KOSDAQ", operating_final, role_metadata)
    role_assignment_pass = all(row["status"] == "PASS" for row in role_validation)
    role_class_mismatch = []
    for family in ("COMBO1", "COMBO2"):
        for row in role_metadata["markets"]["KOSDAQ"][family]:
            derived = classify_role_combo(row.get("role_1"), row.get("role_2")).warning_class
            if derived != row.get("confirmation_type"):
                role_class_mismatch.append(row["candidate_id"])
    expected_default = operating_final.loc[
        operating_final["model_family"].eq("COMBO2") & operating_final["display_slot"].eq(1), "candidate_id"
    ].item()
    hard_pass = (
        not frozen_drift
        and not operating_file_drift
        and set(operating_manifest["combo1_candidates"] + operating_manifest["combo2_candidates"]) == set(operating_final["candidate_id"].astype(str))
        and operating_manifest["previous_combo2_removed"] == "combo2_m6_k3_l2_32c73aa82d8abc21"
        and operating_manifest["combo2_added"] == "combo2_m7_k3_l2_1e7182522962de01"
        and role_assignment_pass
        and not role_class_mismatch
        and final_order == expected_order
        and len(snapshot) == 10
        and chart_parity == 0
        and candidate_after_basis == 0
        and component_after_basis == 0
        and benchmark_after_basis == 0
        and metric_delta <= 5e-9
        and unavailable_as_risk_on == 0
        and payload["ui_side_model_calculation_count"] == 0
        and not forbidden_hits
        and payload["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
        and payload["final_t1_application_count"] == 1
        and payload["invalid_component_as_risk_on_count"] == 0
    )
    return {
        "gate": "PASS_KOSDAQ_MACRO7_D3_ROLE_AWARE_OPERATING" if hard_pass else "FAIL_KOSDAQ_MACRO7_D3_ROLE_AWARE_OPERATING",
        "frozen_asset_drift": frozen_drift,
        "operating_file_drift": operating_file_drift,
        "role_class_mismatch": role_class_mismatch,
        "final10_count": len(snapshot),
        "final10_order_exact": final_order == expected_order,
        "chart_state_parity_mismatch": chart_parity,
        "candidate_history_after_basis_count": candidate_after_basis,
        "component_history_after_basis_count": component_after_basis,
        "benchmark_history_after_basis_count": benchmark_after_basis,
        "frozen_display_metric_max_abs_delta": metric_delta,
        "unavailable_as_risk_on_count": unavailable_as_risk_on,
        "forbidden_runtime_dependency_hits": forbidden_hits,
        "ui_side_model_calculation_count": payload["ui_side_model_calculation_count"],
        "default_selected_candidate": expected_default,
        "selection_semantics": "USER_LOCKED_MAIN_CONFIRM_ROLE_ASSIGNMENTS",
        "main_assignment": True,
        "role_assignment_validation": role_validation,
        "payload_shapes": {key: list(payload[key].shape) for key in ["candidate_history", "component_history", "component_chart_history", "benchmark_history", "performance_history", "frozen_display_metrics"]},
        "live_merge": payload["merge"],
    }


def _report(result: dict[str, Any]) -> str:
    lines = [
        "# KOSDAQ Final10 Role-Aware Operating Validation",
        "",
        f"- Gate: `{result['gate']}`",
        "- Scope: user-locked Final10, Official T+1 parity, presentation lineage, and role-aware stage mapping.",
        f"- Final10: `{result['final10_count']}`; exact D0 order: `{result['final10_order_exact']}`",
        f"- Default display candidate: `{result['default_selected_candidate']}`",
        f"- UI initial-display semantics: `{result['selection_semantics']}`; Main assignment: `{result['main_assignment']}`",
        "",
        "## Payload Checks",
        "",
        f"- Chart state parity mismatch: `{result['chart_state_parity_mismatch']}`",
        f"- Candidate history after basis date: `{result['candidate_history_after_basis_count']}`",
        f"- Component history after parent basis date: `{result['component_history_after_basis_count']}`",
        f"- Benchmark history after candidate basis date: `{result['benchmark_history_after_basis_count']}`",
        f"- Frozen display metric max absolute delta: `{result['frozen_display_metric_max_abs_delta']:.3e}`",
        f"- UNAVAILABLE interpreted as Risk-on: `{result['unavailable_as_risk_on_count']}`",
        f"- UI-side model calculation count: `{result['ui_side_model_calculation_count']}`",
        f"- Presentation runtime forbidden dependency hits: `{len(result['forbidden_runtime_dependency_hits'])}`",
        f"- Frozen baseline asset drift: `{len(result['frozen_asset_drift'])}`",
        f"- Operating overlay manifest drift: `{len(result['operating_file_drift'])}`",
        f"- Role / E-M-H confirmation mismatch: `{len(result['role_class_mismatch'])}`",
        "",
        "## Payload Shapes",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in result["payload_shapes"].items())
    lines.extend(["", "## Live Boundary", "", *[f"- {key}: `{value}`" for key, value in result["live_merge"].items()]])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    outcome = validate()
    REPORT.write_text(_report(outcome), encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False, indent=2, default=str))
    if not outcome["gate"].startswith("PASS_"):
        raise SystemExit(1)
