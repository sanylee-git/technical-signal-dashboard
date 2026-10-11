from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from dashboard_timepoints import candidate_signal_position_rows_at_offsets
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
    assert _candidate_label(combo1_main1).startswith("[조합1 · main · H] 균형형 + 추세지속형")
    assert combo1_main1["display_role"] == "Main1 · 균형형 + 추세지속형"
    assert combo1_confirm["candidate_id"] == "f4d9115064635c283f9f04d5"
    assert _candidate_label(combo1_confirm).endswith("[조합1 · Confirm · H] 공격진입형 (지표 11개/K7/L5)")
    assert combo2_main1["candidate_id"] == "6b4595522bbed808d41be978"
    assert _candidate_label(combo2_main1).startswith("[조합2 · main · H] 균형형 + 추세지속형")
    assert combo2_main1["display_role"] == "Main1 · 균형형 + 추세지속형"
    assert combo2_confirm["candidate_id"] == "e6d450aa79ca39a713ba2558"
    assert _candidate_label(combo2_confirm).endswith("[조합2 · Confirm · E] 보수방어형 + 민감감지형 (조합1 8개/K5/L4)")
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

    assert "min-width:1848px" in html
    assert "white-space:nowrap;overflow-wrap:normal" in html
    assert html.count("<table ") == 1
    assert html.count("</table>") == 1
    assert "<div class='macro-backtest-table-wrap' style='width:100%;overflow-x:auto'><table" in html
    assert "width:380px" in html
    assert html.count("<col style='width:87px'>") == 2
    assert html.count("<col style='width:100px'>") == 4
    assert html.count("<col style='width:106px'>") == 4
    assert all(label in html for label in ("1개월 전", "2주 전", "1주 전", "오늘"))
    assert all(label in html for label in ("근거 신호", "당시 포지션", "Official T+1 결과"))
    assert html.count("<th colspan='2'") == 4
    assert html.count("<th rowspan='2'") == 9
    history = payload["candidate_history"].loc[lambda frame: frame["candidate_id"].eq(candidate.candidate_id)]
    assert history["signal_risk_state"].isin([0, 1]).all()
    assert history["official_t1_risk_off"].isin([0, 1]).all()
    assert "(R-off)" in html or "(R-on)" in html
    combo2_rows = final.loc[final["model_family"].eq("COMBO2")].set_index("candidate_id")
    combo2_ordered_ids = [
        "6b4595522bbed808d41be978",
        "e6d450aa79ca39a713ba2558",
        "b524905cfdecdc45c5cfc205",
        "3e58ad167be4bb0aad010eb9",
        "56965121941b6abcf928fe96",
    ]
    combo2_labels = [_candidate_label(combo2_rows.loc[candidate_id]) for candidate_id in combo2_ordered_ids]
    assert [html.index(label) for label in combo2_labels] == sorted(html.index(label) for label in combo2_labels)

    combo1_rows = final.loc[final["model_family"].eq("COMBO1")].set_index("candidate_id")
    combo1_ordered_ids = [
        "da862ec08d016b6f056c71d4",
        "3b836baf07044098ee443d40",
        "cc58a67d98a9db7b6228a5b6",
        "e4ad56aa66de8a3f2fb7c645",
        "f4d9115064635c283f9f04d5",
    ]
    combo1_labels = [_candidate_label(combo1_rows.loc[candidate_id]) for candidate_id in combo1_ordered_ids]
    combo1_html = _backtest_table(payload, "COMBO1", combo1_ordered_ids[0], final)
    assert "min-width:1848px" in combo1_html and "width:380px" in combo1_html
    assert "white-space:nowrap;overflow-wrap:normal" in combo1_html
    assert [combo1_html.index(label) for label in combo1_labels] == sorted(combo1_html.index(label) for label in combo1_labels)


def test_spx_combo2_history_keeps_raw_signal_and_official_t1_parity(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    snapshot = payload["snapshot"].set_index("candidate_id")
    history = payload["candidate_history"]
    for candidate in final.itertuples(index=False):
        candidate_history = history.loc[history["candidate_id"].astype(str).eq(str(candidate.candidate_id))].sort_values("date")
        signal = candidate_history["signal_risk_state"].astype(int).reset_index(drop=True)
        position = candidate_history["official_t1_risk_off"].astype(int).reset_index(drop=True)
        assert signal.isin([0, 1]).all()
        assert position.isin([0, 1]).all()
        if str(candidate.model_family).upper() == "COMBO1":
            assert position.tolist() == signal.tolist()
            signal_lag = 0
        else:
            assert position.iloc[1:].tolist() == signal.iloc[:-1].tolist()
            signal_lag = 1
        pairs = candidate_signal_position_rows_at_offsets(
            history, candidate.candidate_id, snapshot.loc[candidate.candidate_id, "basis_date"],
            signal_state_col="signal_risk_state", position_state_col="official_t1_risk_off",
            offsets=(21, 10, 5, 0), valid_col="valid_signal", signal_lag_sessions=signal_lag,
        )
        assert all(pair["aligned"] for pair in pairs.values() if pair["application_row"] is not None)


def test_spx_backtest_table_uses_signal_day_count_when_live_signal_count_is_present(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    candidate = final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order").iloc[0]
    state = payload["snapshot"].set_index("candidate_id").loc[candidate["candidate_id"]]
    history = payload["candidate_history"].copy()
    history["signal_active_count"] = history["active_count"]
    candidate_history = history.loc[history["candidate_id"].astype(str).eq(str(candidate["candidate_id"]))].sort_values("date")
    candidate_history = candidate_history.reset_index(drop=True)
    application_position = candidate_history.index[pd.to_datetime(candidate_history["date"]).eq(pd.Timestamp(state["basis_date"]))][0]
    signal_date = pd.Timestamp(candidate_history.iloc[application_position - 1]["date"])
    mask = history["candidate_id"].astype(str).eq(str(candidate["candidate_id"])) & pd.to_datetime(history["date"]).eq(signal_date)
    history.loc[mask, "active_count"] = int(state["K"])
    history.loc[mask, "signal_active_count"] = int(state["L"])
    adjusted_payload = {**payload, "candidate_history": history}

    html = _backtest_table(adjusted_payload, "COMBO2", str(candidate["candidate_id"]), final)
    candidate_row = next(row for row in html.split("<tr") if _candidate_label(candidate) in row)

    assert f"{int(state['L'])}/K{int(state['K'])}/L{int(state['L'])}/{int(candidate['n_or_m'])}" in candidate_row
    assert f"{int(state['K'])}/K{int(state['K'])}/L{int(state['L'])}/{int(candidate['n_or_m'])}" not in candidate_row
