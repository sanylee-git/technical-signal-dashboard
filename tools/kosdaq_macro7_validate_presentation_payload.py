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


ASSETS = ROOT / "kosdaq_macro7_assets"
REPORT = ROOT / "reports/kosdaq_macro7_d2_1_presentation_payload.md"
PRE_D2_1_IMMUTABLE = {
    "kosdaq_macro7_assets/kosdaq_macro7_final10.csv": "2048053e07be73fb76b6a8a6ee4b8ba0fe070ab13b52f66f4185db717c454551",
    "kosdaq_macro7_assets/kosdaq_macro7_combo2_child_mapping.csv": "0ab2fe1e202bad7014fe2c263dc0c60fc3247972511df95f446e2fafa2e7e5d3",
    "kosdaq_macro7_assets/kosdaq_macro7_final_manifest.json": "7353c92265f65012eb7e0f3c56b2503724ccd78a77d99203529728d3a690bf96",
    "kosdaq_macro7_assets/kosdaq_macro7_signal_definitions.csv": "eed8725834e61e56b966bac5327542f7b332d1d441a8fadd6b4d99221e2bccac",
    "kosdaq_macro7_assets/kosdaq_macro7_frozen_asset_manifest.json": "1f8db9dacb57d31744832964f86a86487892d8d692577c6cfb7c8adf86a1f10c",
    "kosdaq_macro7_assets/kosdaq_macro7_live_source_contract.json": "607229b7d2e8cea70819fd424c8cd5a7c526cdd9d4b8efd9d5a7bd854b95a191",
    "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_asset.parquet": "44e485bbb85c1507281df2febadeaa3e9179d278bbc98b9da52e8ab277c810f7",
    "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_contract.json": "d24c05fa6a29fc5dc9b54d1b4dd0ebbcaa64cfe182b3d09dbd15ffa5ea2122d4",
    "kosdaq_macro7_runtime/frozen_replay.py": "d25a48342ffd0b4bfebb0af96b0203a96b69d39cb4b335b709db6d4ccd03465b",
    "kosdaq_macro7_runtime/live_runtime.py": "a91853afa1b4f62bc16e09c046e0386c20fc0b756ea6c1a478a3e94545176600",
    "kosdaq_macro7_runtime/live_sources.py": "d137cd3993b7eba758f3c4f24ef9e785e69c84cdc728174a6789b4cc41164d24",
    "kosdaq_macro7_runtime/market_calendar.py": "e966859b89a7d285dda4dff475beee8714954e109284f1f581586676fc77709d",
    "tools/kosdaq_macro7_validate_live_runtime.py": "9188279db30d038fc229b1a9c9e5edd825136da615cfcbe62fb770828ee14f89",
    "tests/test_kosdaq_macro7_d2_live_runtime.py": "f53803e22e8bfccff18d274e8b9739d9e4bdcf68c058ed38d4d8e7c3c7b6e24c",
    "reports/kosdaq_macro7_d2_live_runtime_validation.md": "17b45da3789a82ad0c2db779ded7f867e739e0a2cacf52f3ab7dcadd6a26977b",
}


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
    immutable_drift = [path for path, expected in PRE_D2_1_IMMUTABLE.items() if _sha256(ROOT / path) != expected]
    contract = json.loads((ASSETS / "kosdaq_macro7_presentation_contract.json").read_text(encoding="utf-8"))
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
    hard_pass = (
        not immutable_drift
        and contract["default_selected_candidate"] == "combo2_m7_k4_l3_58c1eaea19e6d371"
        and contract["selection_semantics"] == "UI_INITIAL_DISPLAY_ONLY"
        and contract["main_assignment"] is False
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
        "gate": "PASS_KOSDAQ_MACRO7_D2_1_PRESENTATION_PAYLOAD_READY" if hard_pass else "FAIL_KOSDAQ_MACRO7_D2_1_PRESENTATION_PAYLOAD",
        "immutable_drift": immutable_drift,
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
        "default_selected_candidate": contract["default_selected_candidate"],
        "selection_semantics": contract["selection_semantics"],
        "main_assignment": contract["main_assignment"],
        "payload_shapes": {key: list(payload[key].shape) for key in ["candidate_history", "component_history", "component_chart_history", "benchmark_history", "performance_history", "frozen_display_metrics"]},
        "live_merge": payload["merge"],
    }


def _report(result: dict[str, Any]) -> str:
    lines = [
        "# KOSDAQ Macro7 D2.1 Presentation Payload Validation",
        "",
        f"- Gate: `{result['gate']}`",
        "- Scope: chart-ready presentation payload only; Stage 3 state and Live semantics are unchanged.",
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
        f"- D0-D2 immutable drift: `{len(result['immutable_drift'])}`",
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
