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


def test_b2r_top_summary_is_two_line_korean_grouped() -> None:
    metrics = pd.DataFrame(
        [
            {"candidate_id": "c2_a", "model_type": "combo2"},
            {"candidate_id": "c2_b", "model_type": "combo2"},
            {"candidate_id": "c1_a", "model_type": "combo1"},
        ]
    )
    rows = [
        {"candidate_id": "c2_a", "calculable": True, "raw_risk_state": 1, "basis_date": "2026-07-31"},
        {"candidate_id": "c2_b", "calculable": True, "raw_risk_state": 0, "basis_date": "2026-07-31"},
        {"candidate_id": "c1_a", "calculable": True, "raw_risk_state": 1, "basis_date": "2026-07-30"},
    ]

    html = dash._macro5_kospi_group_summary_html(rows, metrics)

    assert html.index("조합2 계산 가능") < html.index("조합1 계산 가능")
    assert html.index("조합2 Risk-off(위험회피)") < html.index("조합1 Risk-off(위험회피)")
    assert "Combo1" not in html
    assert "Combo2" not in html
    assert html.count("<div") >= 3


def test_b2r_status_wording_removes_duplicate_technical_phrases() -> None:
    selected = pd.Series({"K": 9, "L": 5})
    live = {
        "basis_date": "2026-07-31",
        "active_count": 9,
        "raw_risk_state": 1,
        "t1_position": 0,
        "new_start_signal": 0,
        "new_end_signal": 0,
        "current_state_start_date": "2026-05-26",
        "current_state_trading_days": 47,
    }

    html = dash._macro5_kospi_current_status_html(selected, live, 11, True, ["신용 스트레스", "KOSPI 지수"])

    assert "현재 플래그</b> 9/K9" in html
    assert "신용 스트레스" not in html
    assert "KOSPI 지수" not in html
    assert "현재 상태 시작일</b> <span style='color:#FF8C69;font-weight:700;'>2026-05-26</span>" in html
    assert "지속 거래일</b> <span style='color:#FF8C69;font-weight:700;'>47</span>" in html
    assert "실행</b> 비투자" in html
    assert "오늘 전환 없음" in html
    assert "T+1" not in html
    assert "47거래일 지속" not in html
    assert "기준</b> 시작" not in html
    assert "freshness" not in html
    assert "실행 상태" not in html
    assert "실행 안내" not in html


def test_b2r_current_column_uses_active_count_denominator() -> None:
    html = dash._macro5_kospi_current_chip(
        "candidate",
        {"candidate": {"calculable": True, "raw_risk_state": 1, "active_count": 5, "component_count": 9}},
        start_k=9,
    )

    assert "5/K9" in html
    assert "Risk-off" not in html


def test_b2r_component_status_uses_latest_use_value_and_hides_raw_freshness() -> None:
    component_df = pd.DataFrame(
        [
            {
                "date": "2026-07-31",
                "component_id": "combo1_child",
                "component_order": 1,
                "component_label": "combo1_child",
                "component_risk_state": 1,
            }
        ]
    )
    live_map = {
        "combo1_child": {
            "basis_date": "2026-07-31",
            "freshness_status": "FRESH",
            "lag_krx_sessions": 0,
        }
    }

    html = dash._macro5_kospi_build_component_status_panel(component_df, [], live_map, "combo2")

    assert "최신 사용값" in html
    assert "2026-07-31 · 최신" in html
    assert "FRESH" not in html
    assert "최신날짜" not in html


def test_b2r_render_section_removes_general_technical_captions_and_metric_card() -> None:
    text = SOURCE.read_text()
    section = text.split("def render_macro5_kospi_section", 1)[1].split("def render_macro5_final8_section", 1)[0]

    assert "KOSPI 후보를 최신 데이터로 판단하고 공식 백테스트 결과와 비교합니다." in section
    assert "Live Shadow 상태 · freshness=" not in section
    assert "성과/차트는 Frozen 기준" not in section
    assert "_bt_html5k" not in section
    assert "macro2-backtest-card" not in section
    assert "공식 Frozen 백테스트:" in section
    assert "고급 설정 · 모델 및 데이터 정보" in section
    assert "──────── 조합1 ────────" in section
    assert "[data-baseweb=\"tag\"] span" in section


def test_b2r_preset_main_alias_uses_fixed_slots() -> None:
    combo2 = pd.Series({"model_type": "combo2", "slot": 5, "role": "균형·강건", "m_or_n": 6, "K": 4, "L": 2})
    combo1 = pd.Series({"model_type": "combo1", "slot": 1, "role": "균형 코어", "m_or_n": 11, "K": 9, "L": 5})
    other = pd.Series({"model_type": "combo2", "slot": 6, "role": "성과 코어", "m_or_n": 6, "K": 4, "L": 3})

    assert dash._macro5_kospi_preset_label(combo2) == "[조합2] Main (조합1 6개/K4/L2)"
    assert dash._macro5_kospi_preset_label(combo1) == "[조합1] Main (지표 11개/K9/L5)"
    assert dash._macro5_kospi_preset_label(other) == "[조합2] 성과 코어 (조합1 6개/K4/L3)"


def test_b2r_chart_and_macro4_functions_are_unchanged() -> None:
    assert _function_hash("_macro5_kospi_build_main_chart") == "6f04019fc3b22922fcb7ba892003f0411fdf24b6d24ee436a9e890bb305f9034"
    assert _function_hash("_macro5_kospi_build_component_chart") == "038c2989d689cb4471d7d5ddf50338ec75766cf8789db7dac91966dcc12c254c"
    assert _function_hash("_make_macro6_combo_chart_from_snapshot") == "5b28ab7bee6b85bd8967e11a288329499ad60f9ac0d3badb0a2657a82b758d83"
    assert _function_hash("_build_macro6_component_chart") == "4b7c1ec7b4482ded77e53bcbf407540efdcf9a4d642e18c713d6a67a93a45246"
    assert _function_hash("_build_macro6_indicator_chart") == "7725e3712828ccbb1f2e2d22f06ef5c59492efc8a7ebf359f7cf30d33f4f2231"
    assert _function_hash("render_macro6_proxy_final_section") == "aee0be189842b248add83b71bbb7eeb1efa9a2cb971f7e025486581b725434f1"
