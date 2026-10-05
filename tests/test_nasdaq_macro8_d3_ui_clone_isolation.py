from __future__ import annotations

from pathlib import Path
import sys
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nasdaq_macro8_runtime.frozen_runtime import run_frozen_runtime
from nasdaq_macro8_runtime.presentation_payload import build_presentation_payload
from nasdaq_macro8_ui import STAGE_COLORS, _backtest_table, _candidate_label, _component_chart, _group_stage, _group_summary, _main_chart, _operational_display_final, _practical_final, _snapshot_row


def _macro8_smoke_app() -> None:
    import streamlit as st

    from nasdaq_macro8_ui import render_macro8_nasdaq_section

    render_macro8_nasdaq_section(st.container())


def _macro8_dashboard_entry_smoke_app() -> None:
    from technical_signal_dashboard import main

    main(page="macro8_nasdaq")


@pytest.fixture(scope="module")
def payload() -> dict:
    return build_presentation_payload(run_frozen_runtime())


def _default_candidate(payload: dict) -> str:
    return str(_operational_display_final(payload).loc[lambda frame: frame["model_family"].eq("COMBO2")].iloc[0]["candidate_id"])


def test_payload_is_frozen_only_and_preserves_final20_runtime_state(payload: dict) -> None:
    assert payload["presentation_contract"] == "nasdaq_macro8_frozen_presentation_payload_v2"
    assert payload["runtime_mode"] == "FROZEN_ONLY"
    assert payload["network_access"] is False
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert payload["ui_side_model_calculation_count"] == 0
    assert len(payload["final20"]) == 20
    assert payload["snapshot"]["basis_date"].nunique() == 1
    assert payload["snapshot"]["basis_date"].iloc[0] == "2026-08-21"
    live = payload["live_metrics"].set_index("candidate_id")
    full = payload["frozen_display_metrics"].loc[payload["frozen_display_metrics"]["window"].eq("FULL")].set_index("candidate_id")
    assert (live.loc[full.index, "cagr"] - full["cagr"]).abs().max() < 1e-12
    assert (live.loc[full.index, "mdd"] - full["mdd"]).abs().max() < 1e-12


def test_selected_final10_is_the_fixed_operational_view(payload: dict) -> None:
    practical = _practical_final(payload["final20"])
    assert len(payload["final20"]) == 20
    assert len(practical) == 10
    assert practical["selection_type"].eq("Practical").all()
    assert practical["model_family"].value_counts().to_dict() == {"COMBO1": 5, "COMBO2": 5}
    display = _operational_display_final(payload)
    assert len(display) == 10
    assert display["model_family"].value_counts().to_dict() == {"COMBO1": 5, "COMBO2": 5}
    summary = _group_summary(payload, display)
    assert "조합2 계산 가능 5 / 5" in summary
    assert "조합1 계산 가능 5 / 5" in summary
    assert "/ 10" not in summary


def test_user_final_five_per_combo_are_the_only_display_candidates(payload: dict) -> None:
    display = _operational_display_final(payload)
    assert len(payload["final20"]) == 20
    assert len(display) == 10
    assert display["model_family"].value_counts().to_dict() == {"COMBO2": 5, "COMBO1": 5}
    assert display.groupby(["model_family", "display_vintage"]).size().to_dict() == {
        ("COMBO1", "New"): 4, ("COMBO1", "Old"): 1,
        ("COMBO2", "New"): 3, ("COMBO2", "Old"): 2,
    }
    combo1 = display.loc[display["model_family"].eq("COMBO1")]
    combo2 = display.loc[display["model_family"].eq("COMBO2")]
    assert combo1["candidate_id"].tolist() == [
        "n10|nq5e10_c7a79e5c0e3bd870", "n8|nq5e8_6f60d9e268c12ef1",
        "n12|nq5e12_d972a9f173c64587", "n8|nq5e8_2bd44048f58e2fcd",
        "n12|nq5e12_02afb347b4b9eaf8",
    ]
    assert combo2["candidate_id"].tolist() == [
        "m5|n6|nq5e6_2c78a53ac6e928f8|n7|nq5e7_934189464a0ef2f2|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_d2cd70973210bf4d|n8|nq5e8_f2b2eadb0bc3f323|K3|L1",
        "m7|n10|nq5e10_9bd42da1c1a6841b|n5|nq5e5_6194c950c7d8e169|n6|nq5e6_2c78a53ac6e928f8|n6|nq5e6_ec1d4faea1cff3e8|n7|nq5e7_2b2edceb8bbeb2b4|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L2",
        "nq_c2_e03c993a14c2dfe8", "nq_c2_478558562d45356d", "nq_c2_6230b4f4492e3e15",
    ]
    assert combo1["display_designation"].tolist() == ["MAIN", "Confirm", "Confirm", "Confirm", "Confirm"]
    assert combo2["display_designation"].tolist() == ["MAIN", "Confirm", "Confirm", "Confirm", "Confirm"]
    assert _candidate_label(combo1.iloc[0]).startswith("[조합1 · main] 균형형 + 추세지속형")
    assert _candidate_label(combo2.iloc[0]).startswith("[조합2 · main] 균형형 + 추세지속형")
    assert _candidate_label(combo1.iloc[1]).startswith("[조합1 · Confirm] 보수방어형 + 추세지속형")
    assert _candidate_label(combo2.iloc[1]).startswith("[조합2 · Confirm] 균형형 + 추세지속형")
    assert _candidate_label(combo1.iloc[4]) == "[조합1 · Confirm] 공격진입형 + 민감감지형 (지표 12개/K7/L5)"


def test_combo2_main_defaults_to_selected_existing_candidate(payload: dict) -> None:
    display = _operational_display_final(payload)
    combo2 = display.loc[display["model_family"].eq("COMBO2")]
    assert combo2.iloc[0]["candidate_id"].startswith("m5|")
    assert combo2.iloc[0]["display_name"] == "균형형 + 추세지속형"
    assert combo2.iloc[0]["display_designation"] == "MAIN"
    assert set(display["candidate_id"]).issubset(set(payload["snapshot"]["candidate_id"]))


def test_ui_isolated_from_other_market_runtimes_and_network() -> None:
    ui = (ROOT / "nasdaq_macro8_ui.py").read_text(encoding="utf-8")
    payload = (ROOT / "nasdaq_macro8_runtime/presentation_payload.py").read_text(encoding="utf-8")
    for forbidden in ("kospi_macro5_runtime", "kosdaq_macro7_runtime", "yfinance", "requests", "fetch_"):
        assert forbidden not in ui
        assert forbidden not in payload
    assert "macro8_nasdaq_preset" in ui
    assert "build_presentation_payload" in ui
    assert "FROZEN_ONLY" in payload
    assert "Proxy Only" in ui


def test_stage_palette_separates_investment_and_noninvestment_sides() -> None:
    assert {label: STAGE_COLORS[label] for label in ("매수심화", "매수", "홀드", "매도준비")} == {
        "매수심화": "#15803D", "매수": "#22C55E", "홀드": "#54F2A3", "매도준비": "#A18707",
    }
    assert {label: STAGE_COLORS[label] for label in ("매수준비", "관망", "매도", "매도심화")} == {
        "매수준비": "#FF8C69", "관망": "#EA580C", "매도": "#F05A47", "매도심화": "#DC2626",
    }


def test_combo_chart_contracts_and_ranges(payload: dict) -> None:
    combo2 = _default_candidate(payload)
    state = _snapshot_row(payload, combo2)
    child = payload["component_history"].loc[payload["component_history"]["parent_candidate_id"].eq(combo2)].sort_values("component_order").iloc[0]
    child_fig = _component_chart(payload, combo2, child.component_id, child.component_kind, state.basis_date, 5, show_aux=False)
    assert child.component_kind == "CHILD_COMBO1_RAW_STATE"
    assert child_fig is not None
    assert [trace.name for trace in child_fig.data] == ["NASDAQ 100"]

    combo1 = str(_operational_display_final(payload).loc[lambda frame: frame["model_family"].eq("COMBO1")].iloc[0]["candidate_id"])
    core = payload["component_history"].loc[payload["component_history"]["parent_candidate_id"].eq(combo1)].sort_values("component_order").iloc[0]
    core_fig = _component_chart(payload, combo1, core.component_id, core.component_kind, state.basis_date, 5, show_aux=True)
    assert core.component_kind == "CORE_INDICATOR"
    assert core_fig is not None
    assert "Raw" in [trace.name for trace in core_fig.data]
    assert "NASDAQ 100" in [trace.name for trace in core_fig.data]

    main = _main_chart(payload, combo2, state.basis_date, "all")
    assert main is not None
    assert pd.Timestamp(main.layout.xaxis.range[0]).normalize() == pd.Timestamp("2008-04-01")
    assert pd.Timestamp(main.layout.xaxis.range[1]).normalize() == pd.Timestamp("2026-08-21")


def test_backtest_table_and_dashboard_wiring_are_presentation_only(payload: dict) -> None:
    candidate_id = _default_candidate(payload)
    table = _backtest_table(payload, "COMBO2", candidate_id)
    assert "NASDAQ 100 홀드" in table
    assert "전체 자산 (18Y)" in table
    assert "min-width:1709px" in table
    assert "width:230px" in table
    assert table.count("<col style='width:87px'>") == 2
    assert table.count("<col style='width:104.4px'>") == 8
    assert all(label in table for label in ("1개월 전", "2주 전", "1주 전", "오늘", "신호", "시장단계"))
    assert table.count("<th colspan='2'") == 4
    assert table.count("<th rowspan='2'") == 9
    assert table.count("<tbody><tr") == 1
    assert table.count("<tr style=") == 5
    assert "Return / Calmar" not in table
    assert "균형형 + 추세지속형" in table
    dashboard = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    assert '"macro8_nasdaq": ("NASDAQ MACRO INDICATORS", "🇺🇸 나스닥지표")' in dashboard
    assert "render_macro8_nasdaq_section(_macro8_nasdaq_container)" in dashboard
    contract = json.loads((ROOT / "nasdaq_macro8_assets/nasdaq_macro8_ui_contract.json").read_text(encoding="utf-8"))
    assert contract["gate"] == "PASS_NASDAQ_MACRO8_D3_UI_CLONE_ISOLATION_READY"
    assert contract["presentation_payload_cache"]["candidate_selection_causing_runtime_refetch"] == 0
    assert contract["chart_contract"]["combo2"] == "CHILD_COMBO1_RAW_STATE plus NASDAQ 100 benchmark only"


def test_mixed_group_stage_is_valid_and_not_unavailable(payload: dict) -> None:
    assert _group_stage(["혼조", "혼조"]) == "혼조"
    assert _group_stage(["혼조", "매수"]) == "혼조"
    assert _group_stage(["계산 불가", "혼조"]) == "계산 불가"
    summary = _group_summary(payload)
    line1 = summary.index("<div class='role-aware-stage-line'><b>조합1</b>")
    line2 = summary.index("<div class='role-aware-stage-line'><b>조합2</b>")
    line3 = summary.index("<div class='role-aware-stage-line'><b>조합1+2</b>")
    assert line1 < line2 < line3
    assert summary.count("class='role-aware-stage-line'") == 3
    assert "조합1+2: <span style='color:#FF8C69;font-weight:700'>계산 불가" not in summary
    operating = _group_summary(payload, _operational_display_final(payload))
    assert "조합2 계산 가능 5 / 5" in operating
    assert "조합1 계산 가능 5 / 5" in operating


def test_nasdaq_default_page_smoke_renders_without_exception() -> None:
    app = AppTest.from_function(_macro8_smoke_app).run(timeout=60)
    assert not app.exception
    assert len(app.selectbox) == 2
    assert len(app.expander) >= 5


def test_dashboard_macro8_entry_path_renders_without_exception() -> None:
    app = AppTest.from_function(_macro8_dashboard_entry_smoke_app).run(timeout=90)
    assert not app.exception
    assert any("나스닥지표" in heading.value for heading in app.get("markdown"))
