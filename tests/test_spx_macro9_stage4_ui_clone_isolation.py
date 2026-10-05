from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spx_macro9_runtime.presentation_payload import build_presentation_payload
from spx_macro9_runtime.selected_final20_runtime import run_selected_final20_runtime
from spx_macro9_ui import _backtest_table, _candidate_label, _display_final, _on_k_html


EXPECTED_COMBO1 = [
    "da862ec08d016b6f056c71d4",
    "e4ad56aa66de8a3f2fb7c645",
    "f4d9115064635c283f9f04d5",
    "3b836baf07044098ee443d40",
    "cc58a67d98a9db7b6228a5b6",
]
EXPECTED_COMBO2 = [
    "6b4595522bbed808d41be978",
    "56965121941b6abcf928fe96",
    "e6d450aa79ca39a713ba2558",
    "b524905cfdecdc45c5cfc205",
    "3e58ad167be4bb0aad010eb9",
]


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    return build_presentation_payload(run_selected_final20_runtime(provider_frames={}))


def test_spx_selected_final10_payload_uses_pinned_models_and_lineage(payload: dict[str, object]) -> None:
    final = payload["final10"]
    assert len(final) == 10
    assert final["model_family"].value_counts().to_dict() == {"COMBO1": 5, "COMBO2": 5}
    assert _display_final(final).shape[0] == 10
    assert final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO1
    assert final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO2
    assert final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")["display_role"].tolist() == [
        "Main1 · 균형형 + 추세지속형",
        "보수방어형 + 추세지속형",
        "공격진입형",
        "보수방어형 + 민감감지형",
        "공격진입형 + 민감감지형",
    ]
    assert final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")["display_role"].tolist() == [
        "Main1 · 균형형 + 추세지속형",
        "균형형 + 추세지속형",
        "보수방어형 + 민감감지형",
        "균형형",
        "공격진입형 + 민감감지형",
    ]
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert payload["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert payload["final_t1_application_count"] == 1
    assert payload["ui_side_model_calculation_count"] == 0
    assert set(payload["snapshot"]["basis_date"]) == {"2026-08-21"}
    assert set(payload["benchmark_history"]["candidate_id"]) == set(final["candidate_id"])


def test_spx_selected_final10_payload_has_component_and_chart_history(payload: dict[str, object]) -> None:
    assert payload["candidate_history"]["candidate_id"].nunique() == 10
    assert payload["component_history"]["parent_candidate_id"].nunique() == 10
    assert set(payload["component_history"]["component_kind"]) <= {
        "CORE_INDICATOR",
        "CHILD_COMBO1_RAW_STATE",
    }
    chart = payload["component_chart_history"]
    assert chart["component_id"].nunique() == 69
    assert pd.to_datetime(chart["date"]).max() == pd.Timestamp("2026-08-21")


def test_spx_combo2_main1_is_the_default_and_tab_uses_operator_ui(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    combo1 = final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")
    combo2 = final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")
    combo1_main1, combo1_confirm = combo1.iloc[0], combo1.iloc[2]
    combo2_main1, combo2_confirm = combo2.iloc[0], combo2.iloc[2]
    assert combo1_main1["candidate_id"] == "da862ec08d016b6f056c71d4"
    assert _candidate_label(combo1_main1).startswith("[조합1 · main] 균형형 + 추세지속형")
    assert combo1_main1["display_role"] == "Main1 · 균형형 + 추세지속형"
    assert combo1_confirm["candidate_id"] == "f4d9115064635c283f9f04d5"
    assert _candidate_label(combo1_confirm).endswith("[조합1 · Confirm] 공격진입형 (지표 11개/K7/L5)")
    assert combo2_main1["candidate_id"] == "6b4595522bbed808d41be978"
    assert _candidate_label(combo2_main1).startswith("[조합2 · main] 균형형 + 추세지속형")
    assert combo2_main1["display_role"] == "Main1 · 균형형 + 추세지속형"
    assert combo2_confirm["candidate_id"] == "e6d450aa79ca39a713ba2558"
    assert _candidate_label(combo2_confirm).endswith("[조합2 · Confirm] 보수방어형 + 민감감지형 (조합1 8개/K5/L4)")
    assert combo2.iloc[0]["candidate_id"] == "6b4595522bbed808d41be978"

    ui = (ROOT / "spx_macro9_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    assert "run_selected_final20_runtime" in ui
    assert "macro9_spx_preset_5x5" in ui
    assert "render_macro9_spx_section" in app
    assert "render_snp2_combo1_trial_section" not in app


def test_spx_backtest_table_adds_four_grouped_timepoints_and_keeps_today_week_values(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    combo2 = final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")
    candidate = combo2.iloc[0]
    state = payload["snapshot"].set_index("candidate_id").loc[candidate["candidate_id"]]

    html = _backtest_table(payload, "COMBO2", str(candidate["candidate_id"]), final)

    assert "min-width:1693.02px" in html
    assert "width:214.02px" in html
    assert html.count("<col style='width:87px'>") == 2
    assert html.count("<col style='width:104.4px'>") == 8
    assert all(label in html for label in ("1개월 전", "2주 전", "1주 전", "오늘"))
    assert html.count("<th colspan='2'") == 4
    assert html.count("<th rowspan='2'") == 9
    assert _on_k_html(state.week_ago_active_count, state.K, state.week_ago_raw_risk_state) in html
    assert _on_k_html(state.active_count, state.K, state.raw_risk_state) in html
    expected_r = "R-off" if int(state.raw_risk_state) == 1 else "R-on"
    assert f"({expected_r})" in html
