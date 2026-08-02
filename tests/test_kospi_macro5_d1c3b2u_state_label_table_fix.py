import re
from pathlib import Path

import pandas as pd

import technical_signal_dashboard as dash


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "technical_signal_dashboard.py"
LABEL_RE = re.compile(r"^\[(조합1|조합2)\] .+ \((지표|조합1) \d+개/K\d+/L\d+\)$")


def test_macro5_final9_labels_follow_common_contract() -> None:
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = assets["metrics"].sort_values("slot").reset_index(drop=True)
    component_dict = assets["component_dictionary"]

    assert metrics["candidate_id"].nunique() == 9
    assert metrics["model_type"].map(dash._macro5_kospi_model_type).eq("combo1").sum() == 4
    assert metrics["model_type"].map(dash._macro5_kospi_model_type).eq("combo2").sum() == 5
    labels = [
        dash._macro5_kospi_preset_label(row, len(component_dict[row["candidate_id"]]["component_ids"]))
        for _, row in metrics.iterrows()
    ]

    assert all(LABEL_RE.match(label) for label in labels)
    assert labels[0].startswith("[조합1] Main (지표 11개/K9/L5)")
    assert labels[4].startswith("[조합2] Main (조합1 6개/K4/L2)")


def test_macro6_loaded_labels_follow_common_contract() -> None:
    presets = dash._load_macro6_proxy_final_presets()
    labels = [cfg["label"] for cfg in presets.values() if not dash._macro3_preset_blocking_reasons(cfg)]

    assert labels
    assert all(LABEL_RE.match(label) for label in labels)
    assert all("(" in label and "/K" in label and "/L" in label for label in labels)


def test_macro5_selectbox_table_chart_label_use_same_string() -> None:
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = assets["metrics"].sort_values("slot").reset_index(drop=True)
    selected = metrics.iloc[4]
    component_count = len(assets["component_dictionary"][selected["candidate_id"]]["component_ids"])
    label = dash._macro5_kospi_preset_label(selected, component_count)
    stats = dash._macro5_kospi_build_backtest_stats(metrics, assets["signals"], assets["benchmark"])

    table_html = dash._macro5_kospi_build_backtest_panel(metrics, {}, selected["candidate_id"], "combo2", stats)

    assert label in table_html
    assert label == dash._macro5_kospi_preset_label(selected, component_count)
    assert " · K4/L2" not in label


def test_macro5_candidate_switch_sync_is_before_disabled_multiselect() -> None:
    section = SOURCE.read_text().split("def render_macro5_kospi_section", 1)[1].split("def render_macro5_final8_section", 1)[0]
    sync_idx = section.index('st.session_state["macro5_kospi_selected_codes"] = list(_selected_components5k)')
    multiselect_idx = section.index("st.multiselect(\n                    \"조합 지표\"")

    assert sync_idx < multiselect_idx
    assert "Choose options" not in section


def test_macro5_current_state_span_uses_eval_start_and_latest_raw_state() -> None:
    signal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2007-12-28", "2008-04-01", "2008-04-02", "2008-04-03", "2008-04-04"]),
            "raw_risk_state": [1, 1, 1, 0, 0],
        }
    )

    span = dash._macro5_kospi_current_state_span(signal, "2008-04-01")

    assert span["state_start_text"] == "2008-04-03"
    assert span["duration_text"] == "2"
    assert span["raw_state"] == 0
    assert span["row_count"] == 4


def test_macro5_current_state_span_marks_left_open_eval_state() -> None:
    signal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2008-04-01", "2008-04-02", "2008-04-03"]),
            "raw_risk_state": [1, 1, 1],
        }
    )

    span = dash._macro5_kospi_current_state_span(signal, "2008-04-01")

    assert span["state_start_text"] == "평가기간 이전부터 지속"
    assert span["duration_text"] == "3"
    assert span["raw_state"] == 1


def test_macro5_cycle_counts_use_t1_position_completed_noninvested_episodes() -> None:
    assert dash._macro5_kospi_cycle_counts(pd.Series([1, 1, 0, 0, 1]), short_cycle_days=20) == (1, 1)
    assert dash._macro5_kospi_cycle_counts(pd.Series([0, 0, 1, 1]), short_cycle_days=20) == (0, 0)
    assert dash._macro5_kospi_cycle_counts(pd.Series([1, 0, 0]), short_cycle_days=20) == (0, 0)
    long_episode = pd.Series([1] + [0] * 21 + [1])
    assert dash._macro5_kospi_cycle_counts(long_episode, short_cycle_days=20) == (1, 0)


def test_macro5_tables_hold_first_and_cagr_ratio_on_candidate_rows() -> None:
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = assets["metrics"].sort_values("slot").reset_index(drop=True)
    stats = dash._macro5_kospi_build_backtest_stats(metrics, assets["signals"], assets["benchmark"])
    html = dash._macro5_kospi_build_backtest_panel(metrics, {}, metrics.iloc[4]["candidate_id"], "combo2", stats)

    assert html.find("KOSPI 홀드") < html.find("[조합2]")
    assert "KOSPI 홀드</td>" in html
    assert re.search(r"전체 CAGR.+?\(\d+\.\d{2}x\)", html, re.S)


def test_macro5_combo2_child_labels_do_not_fall_back_to_hash_suffix() -> None:
    assets = dash._load_macro5_kospi_frozen_assets()
    metrics = assets["metrics"].sort_values("slot").reset_index(drop=True)
    candidate_map = {row["candidate_id"]: row for _, row in metrics.iterrows()}
    component_dict = assets["component_dictionary"]
    combo2_id = metrics[metrics["model_type"].map(dash._macro5_kospi_model_type).eq("combo2")].iloc[0]["candidate_id"]
    child_id = component_dict[combo2_id]["component_ids"][0]

    label = dash._macro5_kospi_component_display_label(child_id, candidate_map, component_dict)

    assert label.startswith("[조합1]")
    assert dash._macro5_kospi_suffix(child_id) not in label


def test_component_status_on_flag_color_is_orange_without_default_change() -> None:
    component_df = pd.DataFrame(
        [
            {
                "date": "2026-07-31",
                "component_id": "kospi_rsi__x",
                "component_order": 1,
                "component_label": "kospi_rsi · x",
                "component_risk_state": 1,
            }
        ]
    )
    html = dash._macro5_kospi_build_component_status_panel(component_df, [], {}, "combo1")

    assert "#FF8C69" in html
    assert "#4BFFB3" in dash._macro_status_circle(True)
