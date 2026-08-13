import ast
import hashlib
from pathlib import Path

import pandas as pd

import technical_signal_dashboard as dash


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "technical_signal_dashboard.py"


def _function_hash(name: str) -> str:
    source = SOURCE.read_text()
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest()
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for sub in ast.walk(node):
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return hashlib.sha256(ast.get_source_segment(source, sub).encode()).hexdigest()
    raise AssertionError(f"function not found: {name}")


def test_macro5_b1_group_summary_uses_existing_candidate_rows() -> None:
    metrics = pd.DataFrame(
        [
            {"candidate_id": "c2_a", "model_type": "combo2"},
            {"candidate_id": "c2_b", "model_type": "COMBO2"},
            {"candidate_id": "c1_a", "model_type": "combo1"},
        ]
    )
    rows = [
        {"candidate_id": "c2_a", "calculable": True, "raw_risk_state": 1, "basis_date": "2026-07-31"},
        {"candidate_id": "c2_b", "calculable": False, "raw_risk_state": 0, "basis_date": "2026-07-31"},
        {"candidate_id": "c1_a", "calculable": True, "raw_risk_state": 0, "basis_date": "2026-07-31"},
    ]

    html = dash._macro5_kospi_group_summary_html(rows, metrics)

    assert "조합2 계산 가능 1 / 2" in html
    assert "계산 불가 1" in html
    assert "조합2 Risk-off(위험회피) 1/2" in html
    assert "조합1 계산 가능 1 / 1" in html
    assert "조합1 Risk-off(위험회피) 0/1" in html
    assert "기준일 2026-07-31" in html
    assert "Combo2" not in html
    assert "Combo1" not in html


def test_macro_runtime_pages_do_not_require_favorites_file_io() -> None:
    for page in ("market_macro", "macro", "macro2", "macro3", "macro5_kospi", "macro6", "market"):
        assert dash._page_needs_favorites(page) is False

    for page in ("signal", "signal2", "signal3", "all"):
        assert dash._page_needs_favorites(page) is True


def test_macro5_b1_backtest_panel_splits_models_and_hides_internal_fields() -> None:
    metrics = pd.DataFrame(
        [
            {
                "candidate_id": "combo2_hash_should_not_render",
                "model_type": "combo2",
                "slot": 1,
                "role": "균형",
                "m_or_n": 6,
                "K": 4,
                "L": 2,
                "suffix": "hidden_suffix",
                "cagr": 0.21,
                "mdd": -0.12,
                "calmar": 1.7,
                "risk_off_ratio": 0.4,
                "annual_turnover": 1.2,
            },
            {
                "candidate_id": "combo1_hash_should_not_render",
                "model_type": "combo1",
                "slot": 6,
                "role": "방어",
                "m_or_n": 11,
                "K": 9,
                "L": 5,
                "suffix": "hidden_suffix",
                "cagr": 0.19,
                "mdd": -0.13,
                "calmar": 1.4,
                "risk_off_ratio": 0.3,
                "annual_turnover": 1.0,
            },
        ]
    )
    live = {
        "combo2_hash_should_not_render": {"calculable": True, "raw_risk_state": 1, "active_count": 4, "component_count": 6},
        "combo1_hash_should_not_render": {"calculable": True, "raw_risk_state": 0, "active_count": 7, "component_count": 11},
    }

    combo2_html = dash._macro5_kospi_build_backtest_panel(metrics, live, "combo2_hash_should_not_render", "combo2")
    combo1_html = dash._macro5_kospi_build_backtest_panel(metrics, live, "combo1_hash_should_not_render", "combo1")

    assert "균형" in combo2_html
    assert "방어" not in combo2_html
    assert "4/K4" in combo2_html
    assert "방어" in combo1_html
    assert "균형" not in combo1_html
    assert "7/K9" in combo1_html
    for html in (combo2_html, combo1_html):
        assert "source_signal_parity" not in html
        assert "hidden_suffix" not in html
        assert "combo2_hash_should_not_render" not in html
        assert "combo1_hash_should_not_render" not in html


def test_macro5_b1_component_status_panel_only_uses_selected_components() -> None:
    component_df = pd.DataFrame(
        [
            {
                "date": "2026-07-31",
                "component_id": "kospi_rsi__RSI14_LB80_Q20_80__abc",
                "component_order": 1,
                "component_label": "kospi_rsi · RSI14_LB80_Q20_80",
                "component_risk_state": 1,
            },
            {
                "date": "2026-07-31",
                "component_id": "vix_level__EMA5_W120_S35_E10__def",
                "component_order": 2,
                "component_label": "vix_level · EMA5_W120_S35_E10",
                "component_risk_state": 0,
            },
        ]
    )
    source_rows = [
        {
            "source_id": "kospi_ohlcv",
            "provider": "yahoo",
            "freshness_status": "FRESH",
            "actual_latest_krx_aligned_date": "2026-07-31",
            "lag_krx_sessions": 0,
        },
        {
            "source_id": "vix",
            "provider": "fred",
            "freshness_status": "FRESH",
            "actual_latest_krx_aligned_date": "2026-07-31",
            "lag_krx_sessions": 0,
        },
    ]

    html = dash._macro5_kospi_build_component_status_panel(component_df, source_rows, {}, "combo1")

    assert "KOSPI RSI" in html
    assert "VIX" in html
    assert "2026-07-31" in html
    assert "Final9" not in html


def test_macro5_b1_render_section_has_split_expanders_and_no_general_dataframe() -> None:
    text = SOURCE.read_text()
    section = text.split("def render_macro5_kospi_section", 1)[1].split("def render_macro5_final8_section", 1)[0]

    assert 'with st.expander("백테스트 비교 보기 · 조합2", expanded=False)' in section
    assert 'with st.expander("백테스트 비교 보기 · 조합1", expanded=False)' in section
    assert 'with st.expander("백테스트 비교 보기", expanded=False)' not in section
    assert "st.dataframe(_compare5k" not in section
    assert "st.dataframe(_status_view5k" not in section
    assert "고급 설정 · 모델 및 데이터 정보" in section
    assert "_bt_html5k" not in section


def test_macro5_b1_chart_and_macro4_functions_are_unchanged() -> None:
    assert _function_hash("_macro5_kospi_build_main_chart") == "139e595560114d98c4214e6e2421f8fd626fa14cc6bdfbc9b2f2e4332d104b66"
    assert _function_hash("_macro5_kospi_build_component_chart") == "fba1a49263474867b229aceb804783a08e28ec23792939175108e1aaada299de"
    assert _function_hash("_make_macro6_combo_chart_from_snapshot") == "5b28ab7bee6b85bd8967e11a288329499ad60f9ac0d3badb0a2657a82b758d83"
    assert _function_hash("_build_macro6_component_chart") == "019bc507b5093fae7ad0ef6bea27b36fd297020e2ab6f2bf562b5926d7d8d85d"
    assert _function_hash("_build_macro6_indicator_chart") == "7725e3712828ccbb1f2e2d22f06ef5c59492efc8a7ebf359f7cf30d33f4f2231"
    assert _function_hash("render_macro6_proxy_final_section") == "50bad188866add9f8de5e2317ad7cfb3e9841d7cd15fc7a4767541c4d60b5821"
    assert _function_hash("_build_macro6_status_panel") == "e38378a8559b713f42236edac8d6c7f2bb868f802c140dd7de6d6176fd827f5e"
    assert _function_hash("_build_macro6_backtest_panel") == "2c9fea51aae5e2805b1eac93356d2b19344474ab0b73190da7d4e0e464f2ee5b"
    assert _function_hash("_macro6_state_duration_html") == "c4ca1c10022d45538e13b561aac8ab42f68e5cfc16be31f615e3017f1f870fee"
