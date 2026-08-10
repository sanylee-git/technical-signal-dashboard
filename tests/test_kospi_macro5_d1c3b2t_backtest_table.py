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


def _assets():
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = assets["metrics"].sort_values("slot").reset_index(drop=True)
    stats = dash._macro5_kospi_build_backtest_stats(metrics, assets["signals"], assets["benchmark"])
    return assets, metrics, stats


def test_b2t_backtest_stats_use_frozen_windows_and_existing_metric_parity() -> None:
    _, metrics, stats = _assets()

    assert stats["window"]["frozen_start"] == "2008-04-01"
    assert stats["window"]["frozen_end"] == "2026-07-28"
    assert stats["window"]["ten_year_start"] == "2016-07-28"
    assert stats["hold"]["전체 Risk-off"] == "0.0%"
    assert stats["hold"]["전체 Cycle"] == "-"

    for _, row in metrics.iterrows():
        candidate_stats = stats["candidate"][row["candidate_id"]]
        assert candidate_stats["전체 CAGR"] == dash._macro5_kospi_fmt_pct(row["cagr"], 1)
        assert candidate_stats["전체 MDD"] == dash._macro5_kospi_fmt_pct(row["mdd"], 1)
        assert candidate_stats["전체 Risk-off"] == dash._macro5_kospi_fmt_pct(row["risk_off_ratio"], 1)


def test_b2t_cached_backtest_stats_match_uncached_and_reuse_heavy_calculation(monkeypatch) -> None:
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = dash._macro5_kospi_sort_metrics(assets["metrics"])
    asset_key = assets["backtest_asset_contract_key"]

    assert asset_key == dash._macro5_kospi_frozen_asset_contract_key()
    assert len(asset_key) == 64

    uncached = dash._macro5_kospi_build_backtest_stats(metrics, assets["signals"], assets["benchmark"])
    original = dash._macro5_kospi_build_backtest_stats
    calls = {"count": 0}

    def counted_build_backtest_stats(metrics_arg, signals_arg, benchmark_arg):
        calls["count"] += 1
        return original(metrics_arg, signals_arg, benchmark_arg)

    dash._macro5_kospi_build_backtest_stats_cached.clear()
    monkeypatch.setattr(dash, "_macro5_kospi_build_backtest_stats", counted_build_backtest_stats)

    first = dash._macro5_kospi_build_backtest_stats_cached(asset_key)
    second = dash._macro5_kospi_build_backtest_stats_cached(asset_key)

    assert first == uncached
    assert second == uncached
    assert calls["count"] == 1


def test_b2t_combo2_and_combo1_tables_have_required_columns_and_hold_rows() -> None:
    _, metrics, stats = _assets()
    dates = pd.date_range("2026-08-03", periods=6, freq="B")
    history_rows = []
    live_map = {
        row["candidate_id"]: {
            "calculable": True,
            "raw_risk_state": 1,
            "active_count": int(row["K"]),
            "component_count": int(row["m_or_n"]),
        }
        for _, row in metrics.iterrows()
    }
    for _, row in metrics.iterrows():
        for idx, date in enumerate(dates):
            history_rows.append({
                "candidate_id": row["candidate_id"],
                "date": date,
                "active_count": max(0, int(row["K"]) - (1 if idx == 0 else 0)),
                "raw_risk_state": int(idx > 0),
            })
    history = pd.DataFrame(history_rows)

    combo2 = dash._macro5_kospi_build_backtest_panel(metrics, live_map, metrics.iloc[4]["candidate_id"], "combo2", stats, history)
    combo1 = dash._macro5_kospi_build_backtest_panel(metrics, live_map, metrics.iloc[0]["candidate_id"], "combo1", stats, history)

    required = [
        "역할 / 후보",
        "10Y 자산",
        "전체 자산",
        "전체 CAGR",
        "10Y MDD",
        "전체 MDD",
        "전체 Risk-off",
        "전체 Cycle",
        "짧은 Cycle",
        "1주 전",
        "시장단계(1주 전)",
        "현재",
        "시장단계",
    ]
    for html in (combo2, combo1):
        for column in required:
            assert column in html
        assert "20Y" not in html
        assert "연 전환" not in html
        assert "KOSPI 홀드" in html
        assert "(2." in html or "(1." in html or "(0." in html

    assert combo2.count("<tr") == 7
    assert combo1.count("<tr") == 6
    assert combo2.find("KOSPI 홀드") < combo2.find("[조합2]")
    assert combo1.find("KOSPI 홀드") < combo1.find("[조합1]")


def test_b2t_current_column_uses_live_active_count_over_entry_k() -> None:
    _, metrics, stats = _assets()
    selected_id = metrics.iloc[0]["candidate_id"]
    live_map = {
        selected_id: {
            "calculable": True,
            "raw_risk_state": 1,
            "active_count": 9,
            "component_count": 11,
        }
    }

    html = dash._macro5_kospi_build_backtest_panel(metrics.iloc[[0]], live_map, selected_id, "combo1", stats)

    assert "9/K9" in html
    assert "Risk-off</span>" not in html


def test_b2t_market_stage_label_uses_existing_on_k_l_and_state() -> None:
    assert dash._macro_market_stage_label(5, 4, 2, False) == "매도심화"
    assert dash._macro_market_stage_label(4, 4, 2, False) == "매도"
    assert dash._macro_market_stage_label(3, 4, 2, False) == "매도준비"
    assert dash._macro_market_stage_label(3, 4, 2, True) == "매수준비"
    assert dash._macro_market_stage_label(2, 4, 2, True) == "매수"
    assert dash._macro_market_stage_label(1, 4, 2, True) == "매수심화"
    assert dash._macro_market_stage_label(4, 6, 2, False) == "홀드"
    assert dash._macro_market_stage_label(4, 6, 2, True) == "관망"


def test_b2t_market_stage_html_colors_only_known_labels() -> None:
    expected = {
        "홀드": "#A18707",
        "매수준비": "#54F2A3",
        "매수": "#22C55E",
        "매수심화": "#15803D",
        "관망": "#A18707",
        "매도준비": "#FF8C69",
        "매도": "#F05A47",
        "매도심화": "#DC2626",
        "혼조": "#6B7280",
    }
    for label, color in expected.items():
        html = dash._macro_market_stage_html(label)
        assert label in html
        assert color in html
    assert dash._macro_market_stage_html("계산 불가") == "계산 불가"


def test_b2t_group_market_stage_examples_follow_contract() -> None:
    assert dash._macro_group_market_stage_label(["매도심화", "매도심화", "매수심화", "매수심화"]) == "혼조"
    assert dash._macro_group_market_stage_label(["매도심화", "매도심화", "매도심화", "매수심화", "매수심화"]) == "혼조"
    assert dash._macro_group_market_stage_label(["매도심화", "매도심화", "매도심화", "매수준비", "홀드"]) == "매도"
    assert dash._macro_group_market_stage_label(["매도준비", "매도준비", "홀드", "관망"]) == "매도준비"
    assert dash._macro_group_market_stage_label(["홀드", "홀드", "홀드", "관망"]) == "홀드"
    assert dash._macro_group_market_stage_label(["홀드", "관망", "홀드", "관망"]) == "혼조"
    assert dash._macro_group_market_stage_label(["홀드", "홀드", "관망", "매도준비", "매수준비"]) == "홀드"
    assert dash._macro_group_market_stage_label(["홀드", "계산 불가"]) == "계산 불가"


def test_b2t_combined_group_market_stage_examples_follow_contract() -> None:
    assert dash._macro_combined_group_market_stage_label("매수", "매도") == "혼조"
    assert dash._macro_combined_group_market_stage_label("매수심화", "매도준비") == "혼조"
    assert dash._macro_combined_group_market_stage_label("홀드", "관망") == "혼조"
    assert dash._macro_combined_group_market_stage_label("홀드", "매도") == "매도준비"
    assert dash._macro_combined_group_market_stage_label("매도심화", "매도심화") == "매도심화"
    assert dash._macro_combined_group_market_stage_label("매수", "매수") == "매수"
    assert dash._macro_combined_group_market_stage_label("계산 불가", "매도") == "계산 불가"


def test_b2t_group_market_stage_summary_line_uses_existing_spacing_and_order() -> None:
    html = dash._macro_group_market_stage_summary_html("매도", "관망", "매도준비", "혼조")
    assert "<b>시장단계</b> · 조합1+2:" in html
    assert html.find("조합1+2") < html.find("조합2:") < html.find("조합1:")
    assert html.count("padding:0 10px;") == 2
    assert html.count("→") == 3
    assert "#F05A47" in html
    assert "#A18707" in html


def test_b2t_macro5_group_summary_adds_third_market_stage_line() -> None:
    metrics = pd.DataFrame(
        [
            {"candidate_id": "c2a", "model_type": "combo2", "K": 4, "L": 2},
            {"candidate_id": "c2b", "model_type": "combo2", "K": 4, "L": 2},
            {"candidate_id": "c1a", "model_type": "combo1", "K": 3, "L": 1},
            {"candidate_id": "c1b", "model_type": "combo1", "K": 3, "L": 1},
        ]
    )
    rows = [
        {"candidate_id": "c2a", "calculable": True, "active_count": 4, "raw_risk_state": 1, "basis_date": "2026-08-10"},
        {"candidate_id": "c2b", "calculable": True, "active_count": 4, "raw_risk_state": 1, "basis_date": "2026-08-10"},
        {"candidate_id": "c1a", "calculable": True, "active_count": 1, "raw_risk_state": 1, "basis_date": "2026-08-10"},
        {"candidate_id": "c1b", "calculable": True, "active_count": 1, "raw_risk_state": 1, "basis_date": "2026-08-10"},
    ]
    html = dash._macro5_kospi_group_summary_html(rows, metrics)
    assert "<b>시장단계</b> · 조합1+2:" in html
    assert html.find("계산 가능") < html.find("Risk-off") < html.find("시장단계")
    assert html.count("margin-top:2px;") == 2


def test_b2t_week_ago_state_row_uses_five_trading_sessions_not_calendar_days() -> None:
    dates = pd.to_datetime(["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"])
    history = pd.DataFrame({"date": list(reversed(dates)), "active_count": list(reversed(range(6))), "raw_risk_state": [1, 1, 1, 1, 0, 0]})
    row = dash._macro_week_ago_state_row(history)
    assert pd.Timestamp(row["date"]) == pd.Timestamp("2026-07-27")

    longer = pd.DataFrame({"date": pd.bdate_range("2026-07-20", periods=10), "active_count": range(10), "raw_risk_state": 0})
    row = dash._macro_week_ago_state_row(longer)
    assert int(row["active_count"]) == 4

    assert dash._macro_week_ago_state_row(longer.iloc[:5]) is None


def test_b2t_week_ago_individual_stage_uses_historical_risk_state() -> None:
    risk_on_row = {"active_count": 7, "raw_risk_state": 0}
    risk_off_row = {"active_count": 7, "raw_risk_state": 1}
    assert "홀드" in dash._macro_historical_market_stage_html(risk_on_row, 9, 5, "raw_risk_state")
    assert "관망" in dash._macro_historical_market_stage_html(risk_off_row, 9, 5, "raw_risk_state")
    assert "계산 불가" in dash._macro_historical_current_chip({"active_count": 7}, 9, "raw_risk_state")
    assert "계산 불가" in dash._macro_historical_market_stage_html({"raw_risk_state": 1}, 9, 5, "raw_risk_state")


def test_b2t_chart_and_runtime_functions_are_unchanged_except_macro4_backtest_table() -> None:
    assert _function_hash("_macro5_kospi_build_main_chart") == "6f04019fc3b22922fcb7ba892003f0411fdf24b6d24ee436a9e890bb305f9034"
    assert _function_hash("_macro5_kospi_build_component_chart") == "038c2989d689cb4471d7d5ddf50338ec75766cf8789db7dac91966dcc12c254c"
    assert _function_hash("render_macro6_proxy_final_section") == "2bd3464fbb2b1848cc7e0ceff0457cc9dac06229435875051e12de77a403f326"
    assert _function_hash("_build_macro6_backtest_panel") == "2c9fea51aae5e2805b1eac93356d2b19344474ab0b73190da7d4e0e464f2ee5b"
    assert _function_hash("_make_macro6_combo_chart_from_snapshot") == "5b28ab7bee6b85bd8967e11a288329499ad60f9ac0d3badb0a2657a82b758d83"
