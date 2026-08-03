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


def test_b2t_combo2_and_combo1_tables_have_required_columns_and_hold_rows() -> None:
    _, metrics, stats = _assets()
    live_map = {
        row["candidate_id"]: {
            "calculable": True,
            "raw_risk_state": 1,
            "active_count": int(row["K"]),
            "component_count": int(row["m_or_n"]),
        }
        for _, row in metrics.iterrows()
    }

    combo2 = dash._macro5_kospi_build_backtest_panel(metrics, live_map, metrics.iloc[4]["candidate_id"], "combo2", stats)
    combo1 = dash._macro5_kospi_build_backtest_panel(metrics, live_map, metrics.iloc[0]["candidate_id"], "combo1", stats)

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
        "현재",
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


def test_b2t_chart_macro4_and_runtime_functions_are_unchanged() -> None:
    assert _function_hash("_macro5_kospi_build_main_chart") == "6f04019fc3b22922fcb7ba892003f0411fdf24b6d24ee436a9e890bb305f9034"
    assert _function_hash("_macro5_kospi_build_component_chart") == "0ab6ea0276d1a5f8963a77d4d60bf517d69f74bdaeac3cab46cd9f8978f4d024"
    assert _function_hash("render_macro6_proxy_final_section") == "6eb77cead55b025adf2b10cad2ddd49807852732bd1ba6b87188fe8ca543fc27"
    assert _function_hash("_build_macro6_backtest_panel") == "f0abfee7e2d7df9db87a2c5dd0d30645f135565f42ac8cbfd0632ecc29476f08"
    assert _function_hash("_make_macro6_combo_chart_from_snapshot") == "5b28ab7bee6b85bd8967e11a288329499ad60f9ac0d3badb0a2657a82b758d83"
