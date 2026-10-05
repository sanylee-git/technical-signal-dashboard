from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard_role_aware_market_stage import (
    TIMEPOINTS,
    compute_role_aware_market_outputs,
    format_role_stage_sequence,
    load_role_metadata,
    validate_market_metadata,
)
from nasdaq_macro8_runtime.frozen_runtime import run_frozen_runtime as run_nasdaq_frozen
from nasdaq_macro8_runtime.presentation_payload import build_presentation_payload as build_nasdaq_payload
from nasdaq_macro8_ui import _group_summary as nasdaq_group_summary, _operational_display_final
from spx_macro9_runtime.presentation_payload import build_presentation_payload as build_spx_payload
from spx_macro9_runtime.selected_final20_runtime import run_selected_final20_runtime
from spx_macro9_ui import _display_final, _group_summary as spx_group_summary


def _spx_role_aware_market_app() -> None:
    import streamlit as st

    from spx_macro9_runtime.presentation_payload import build_presentation_payload
    from spx_macro9_runtime.selected_final20_runtime import run_selected_final20_runtime
    from spx_macro9_ui import render_macro9_spx_section

    payload = build_presentation_payload(run_selected_final20_runtime(provider_frames={}))
    confirmed = payload["confirmed_snapshot"].copy().set_index("candidate_id")
    provisional = payload["snapshot"].set_index("candidate_id")
    for column in ("week_ago_basis_date", "week_ago_raw_risk_state", "week_ago_active_count"):
        confirmed[column] = provisional.loc[confirmed.index, column]
    payload["snapshot"] = confirmed.reset_index()
    render_macro9_spx_section(st.container(), payload=payload)


def _nasdaq_role_aware_market_app() -> None:
    import streamlit as st

    from nasdaq_macro8_runtime.frozen_runtime import run_frozen_runtime
    from nasdaq_macro8_runtime.presentation_payload import build_presentation_payload
    from nasdaq_macro8_ui import render_macro8_nasdaq_section

    payload = build_presentation_payload(run_frozen_runtime())
    render_macro8_nasdaq_section(st.container(), payload=payload)


@pytest.fixture(scope="module")
def spx_payload() -> dict:
    payload = build_spx_payload(run_selected_final20_runtime(provider_frames={}))
    confirmed = payload["confirmed_snapshot"].copy()
    provisional = payload["snapshot"].set_index("candidate_id")
    confirmed = confirmed.set_index("candidate_id")
    for column in ("week_ago_basis_date", "week_ago_raw_risk_state", "week_ago_active_count"):
        confirmed[column] = provisional.loc[confirmed.index, column]
    payload["snapshot"] = confirmed.reset_index()
    return payload


@pytest.fixture(scope="module")
def nasdaq_payload() -> dict:
    return build_nasdaq_payload(run_nasdaq_frozen())


@pytest.mark.parametrize("market", ["S&P2", "NASDAQ"])
def test_authoritative_metadata_matches_each_operational_five_plus_five(market, spx_payload, nasdaq_payload) -> None:
    payload = spx_payload if market == "S&P2" else nasdaq_payload
    final = _display_final(payload["final10"]) if market == "S&P2" else _operational_display_final(payload)

    checks = validate_market_metadata(market, final)

    assert len(checks) == 2
    assert all(row["status"] == "PASS" for row in checks)
    assert all(row["candidate_id_exact_match"] == 1 for row in checks)
    assert all(row["main_count"] == 1 and row["confirm_count"] == 4 for row in checks)
    assert all(row["role_1_missing_count"] == 0 and row["invalid_role_combo_count"] == 0 for row in checks)


@pytest.mark.parametrize("market", ["S&P2", "NASDAQ"])
def test_all_four_timepoints_produce_combo_and_overall_explanations(market, spx_payload, nasdaq_payload) -> None:
    payload = spx_payload if market == "S&P2" else nasdaq_payload
    final = _display_final(payload["final10"]) if market == "S&P2" else _operational_display_final(payload)
    outputs = compute_role_aware_market_outputs(
        market, final, payload["snapshot"], payload["candidate_history"]
    )

    assert len(outputs) == 12
    assert {row["combination"] for row in outputs} == {"COMBO1", "COMBO2", "OVERALL"}
    assert {row["timepoint_code"] for row in outputs} == {code for _, code, _ in TIMEPOINTS}
    assert all(row["metadata_status"] == "PASS" for row in outputs)
    assert all(row["state_status"] == "PASS" for row in outputs)
    assert all(row["stage_code"] in {"BUY", "WEAK_CAUTION", "STRONG_CAUTION", "SELL"} for row in outputs)
    assert all(row["reason_code"] for row in outputs)
    for row in outputs:
        if row["combination"] in {"COMBO1", "COMBO2"}:
            assert row["model_count"] == 5
            assert row["risk_off_count"] == row["E_off"] + row["M_off"] + row["H_off"]


def test_market_summary_displays_role_aware_states_and_captures_legacy_payload(spx_payload, nasdaq_payload) -> None:
    cases = (
        ("S&P2", spx_payload, _display_final(spx_payload["final10"]), spx_group_summary),
        ("NASDAQ", nasdaq_payload, _operational_display_final(nasdaq_payload), nasdaq_group_summary),
    )
    for market, payload, final, summary_fn in cases:
        capture: dict[str, object] = {}
        html = summary_fn(payload, final, output_capture=capture)

        assert "시장단계 (1개월 전 → 2주 전 → 1주 전 → 오늘)" in html
        expected_lines = (
            ("조합1", "COMBO1"),
            ("조합2", "COMBO2"),
            ("조합1+2", "OVERALL"),
        )
        rendered_lines = [
            f"<div class='role-aware-stage-line'><b>{label}</b> "
            f"{format_role_stage_sequence(capture['role_aware_market_stage'], combination)}</div>"
            for label, combination in expected_lines
        ]
        stage_section = html[html.index("<b>시장단계") :]
        positions = [stage_section.index(line) for line in rendered_lines]
        assert positions == sorted(positions)
        assert stage_section.count("class='role-aware-stage-line'") == 3
        assert "padding:0 10px'>|</span>" not in stage_section
        assert "(Risk-on)" in html or "(Risk-off)" in html
        assert len(capture["legacy_market_stage"]) == 12
        assert len(capture["role_aware_market_stage"]) == 12
        assert {row["combination"] for row in capture["legacy_market_stage"]} == {"COMBO1", "COMBO2", "OVERALL"}


def test_role_aware_market_sections_render_with_local_frozen_payloads() -> None:
    for app_fn in (_spx_role_aware_market_app, _nasdaq_role_aware_market_app):
        app = AppTest.from_function(app_fn).run(timeout=90)

        assert not app.exception
        markdown = "\n".join(element.value for element in app.get("markdown"))
        assert "시장단계 (1개월 전 → 2주 전 → 1주 전 → 오늘)" in markdown
        line_positions = [
            markdown.index(f"<div class='role-aware-stage-line'><b>{label}</b>")
            for label in ("조합1", "조합2", "조합1+2")
        ]
        assert line_positions == sorted(line_positions)
        assert "🟢" in markdown or "🟡" in markdown or "🟠" in markdown or "🔴" in markdown


def test_metadata_candidate_drift_fails_closed(spx_payload) -> None:
    final = _display_final(spx_payload["final10"]).copy()
    final.loc[final.index[0], "candidate_id"] = "not-an-authoritative-candidate"
    outputs = compute_role_aware_market_outputs(
        "S&P2", final, spx_payload["snapshot"], spx_payload["candidate_history"]
    )

    assert all(row["stage_code"] == "UNAVAILABLE" for row in outputs)
    assert all(row["metadata_status"] == "FAIL" for row in outputs)
    assert all("METADATA_VALIDATION_FAILED" in row["unavailable_reason"] for row in outputs)


def test_missing_candidate_risk_state_fails_closed_without_partial_vote(nasdaq_payload) -> None:
    final = _operational_display_final(nasdaq_payload)
    snapshot = nasdaq_payload["snapshot"].copy()
    main_id = str(final.loc[final["model_family"].eq("COMBO1")].iloc[0]["candidate_id"])
    snapshot.loc[snapshot["candidate_id"].astype(str).eq(main_id), "raw_risk_state"] = pd.NA
    outputs = compute_role_aware_market_outputs(
        "NASDAQ", final, snapshot, nasdaq_payload["candidate_history"]
    )
    today_combo1 = next(row for row in outputs if row["timepoint_code"] == "TODAY" and row["combination"] == "COMBO1")
    today_overall = next(row for row in outputs if row["timepoint_code"] == "TODAY" and row["combination"] == "OVERALL")

    assert today_combo1["stage_code"] == "UNAVAILABLE"
    assert "INVALID_OR_MISSING_RISK_STATE" in today_combo1["unavailable_reason"]
    assert today_overall["stage_code"] == "UNAVAILABLE"


def test_metadata_document_has_only_explicit_user_authorized_markets() -> None:
    document = load_role_metadata()

    assert set(document["markets"]) == {"S&P2", "NASDAQ", "KOSPI"}
    assert document["authority"] == "user_explicitly_confirmed"
