import pandas as pd
import pytest

import technical_signal_dashboard as dash


def test_b2v_current_status_is_compact_and_does_not_render_active_component_list() -> None:
    live = {
        "basis_date": "2026-07-31",
        "active_count": 4,
        "raw_risk_state": 1,
        "t1_position": 0,
        "new_start_signal": 1,
        "new_end_signal": 0,
        "current_state_start_date": "2026-07-31",
        "current_state_trading_days": 1,
    }

    html = dash._macro5_kospi_current_status_html(
        pd.Series({"K": 4, "L": 1}),
        live,
        6,
        True,
        ["길게 나오면 안 되는 구성요소"],
    )

    assert "기준일 2026-07-31" in html
    assert "현재 플래그 <span style='color:#FF8C69;font-weight:700;font-variant-numeric:tabular-nums;'>4/K4</span>" in html
    assert "상태 <span" in html
    assert "리스크 사이클 ON" in html
    assert "실행 비투자" in html
    assert "오늘 Risk-off(위험회피) 시작" in html
    assert "길게 나오면 안 되는 구성요소" not in html
    assert "실행 상태" not in html
    assert "실행 안내" not in html


def test_b2v_compact_status_end_signal_sentence() -> None:
    html = dash._macro_compact_status_html(
        basis_date="2026-07-31",
        active_count=2,
        component_count=6,
        risk_state=0,
        execution_position=1,
        start_event=False,
        end_event=True,
        state_start="2026-07-31",
        duration_text="1",
    )

    assert "현재 플래그 <span style='color:#54F2A3;font-weight:700;font-variant-numeric:tabular-nums;'>2/K6</span>" in html
    assert "리스크 사이클 OFF" in html
    assert "실행 투자" in html
    assert "오늘 Risk-off(위험회피) 종료" in html


def test_b2v_state_period_return_uses_benchmark_close_and_sign_color() -> None:
    benchmark = pd.DataFrame(
        {
            "date": ["2026-07-30", "2026-07-31"],
            "kospi_close": [100.0, 110.0],
        }
    )

    values = dash._macro_state_period_return_values(benchmark, "2026-07-30", "2026-07-31")

    assert values == {"text": "+10.0%", "color": dash._MACRO_STATUS_RISK_ON_COLOR}

    negative = dash._macro_state_period_return_values(
        benchmark.assign(kospi_close=[100.0, 90.0]),
        "2026-07-30",
        "2026-07-31",
    )
    assert negative == {"text": "-10.0%", "color": dash._MACRO_STATUS_RISK_OFF_COLOR}


def test_b2v_macro6_status_panel_uses_same_compact_wording() -> None:
    event_df = pd.DataFrame(
        [
            {"date": "2026-07-30", "combo_risk_state": 0, "active_count": 1, "combo_n": 3},
            {
                "date": "2026-07-31",
                "combo_risk_state": 1,
                "active_count": 2,
                "combo_n": 3,
                "combo_start_signal": 1,
                "combo_end_signal": 0,
                "index_flag": 1,
            },
        ]
    )
    status, _table = dash._build_macro6_status_panel(
        benchmark_name="S&P500",
        years=5,
        preset_cfg={"selected_indicators": ["Index"], "combo_k": 2, "combo_l": 1},
        combo_event_df=event_df,
    )

    assert "현재 플래그 <span style='color:#FF8C69;font-weight:700;font-variant-numeric:tabular-nums;'>2/K2</span>" in status
    assert "오늘 Risk-off(위험회피) 시작" in status
    assert "실행 비투자" in status
    assert status.count("2/K2") == 1


def test_b2v_default_preset_is_unique_combo2_main_and_invalid_state_recovers_to_it() -> None:
    metrics = pd.DataFrame(
        [
            {"candidate_id": "combo1_main", "model_type": "combo1", "slot": 1, "role": "균형", "m_or_n": 11, "K": 9, "L": 5},
            {"candidate_id": "combo2_def", "model_type": "combo2", "slot": 4, "role": "방어", "m_or_n": 6, "K": 4, "L": 2},
            {"candidate_id": "combo2_main", "model_type": "combo2", "slot": 5, "role": "균형", "m_or_n": 6, "K": 4, "L": 2},
        ]
    )

    default_id = dash._macro5_kospi_combo2_main_candidate_id(metrics)
    assert default_id == "combo2_main"

    preset_order = ["combo2_def", "combo2_main", "combo1_main"]
    selected = "stale_candidate"
    if selected not in preset_order:
        selected = default_id
    assert selected == "combo2_main"


def test_b2v_default_preset_missing_or_duplicate_main_is_review() -> None:
    duplicate = pd.DataFrame(
        [
            {"candidate_id": "a", "model_type": "combo2", "slot": 5, "role": "균형", "m_or_n": 6, "K": 4, "L": 2},
            {"candidate_id": "b", "model_type": "combo2", "slot": 5, "role": "수익", "m_or_n": 6, "K": 4, "L": 2},
        ]
    )
    missing = pd.DataFrame(
        [{"candidate_id": "a", "model_type": "combo2", "slot": 6, "role": "수익", "m_or_n": 6, "K": 4, "L": 2}]
    )

    with pytest.raises(ValueError, match="REVIEW_KOSPI_MACRO5_D1C3B2V_COMBO2_MAIN_NOT_UNIQUE"):
        dash._macro5_kospi_combo2_main_candidate_id(duplicate)
    with pytest.raises(ValueError, match="REVIEW_KOSPI_MACRO5_D1C3B2V_COMBO2_MAIN_NOT_UNIQUE"):
        dash._macro5_kospi_combo2_main_candidate_id(missing)


def test_b2v_macro4_macro5_backtest_tables_share_fixed_width_contract() -> None:
    macro5_metrics = pd.DataFrame(
        [{"candidate_id": "c5", "model_type": "combo2", "slot": 5, "role": "균형", "m_or_n": 6, "K": 4, "L": 2}]
    )
    macro5_html = dash._macro5_kospi_build_backtest_panel(macro5_metrics, {}, "c5", "combo2", {"hold": {}, "candidate": {}})
    macro6_html = dash._build_macro6_backtest_panel(
        "p1",
        {
            "p1": {
                "kind": "combo2_final8",
                "role_tags": "균형",
                "combo_m": 6,
                "combo_k": 4,
                "combo_l": 2,
                "components": [],
                "metrics": {
                    "10Y 자산": "100",
                    "20Y 자산": "100",
                    "20Y CAGR": "0.0%",
                    "10Y MDD": "-1.0%",
                    "20Y MDD": "-1.0%",
                    "20Y Risk-off": "10.0%",
                    "20Y Cycle": "1",
                    "짧은 Cycle": "0",
                },
            }
        },
        ["p1"],
    )

    for html in (macro5_html, macro6_html):
        assert "macro-backtest-table-wrap" in html
        assert "min-width:1406px" in html
        assert "font-size:11px" in html
        assert "table-layout:fixed" in html
        assert html.count("<col style=") == 13
        assert 'width:12.3%' in html
        for width in ("5.3%", "4.5%", "5.0%", "3.7%", "3.2%", "4.6%"):
            assert html.count(f'width:{width}') == 2
        assert dash._MACRO_BACKTEST_COLGROUP in html

    assert dash._MACRO_BACKTEST_COLGROUP in macro5_html
    assert dash._MACRO_BACKTEST_COLGROUP in macro6_html
