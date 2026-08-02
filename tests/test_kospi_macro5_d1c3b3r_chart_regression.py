from __future__ import annotations

from functools import lru_cache

import pandas as pd

import technical_signal_dashboard as dash
from kospi_macro5_runtime.page_adapter import load_macro5_live_page_data


@lru_cache(maxsize=1)
def _actual_page_data():
    return load_macro5_live_page_data()


@lru_cache(maxsize=1)
def _assets():
    return dash._load_macro5_kospi_frozen_assets()


def _candidate_map(metrics: pd.DataFrame):
    return {str(row["candidate_id"]): row for _, row in metrics.iterrows()}


def test_b3r_actual_page_route_final9_main_charts_all_render_to_basis_date():
    live = _actual_page_data()
    assets = _assets()
    metrics = assets["metrics"]
    assert live["calculation_status"] == "CALCULABLE"
    assert pd.to_datetime(live["benchmark_close_history"]["date"]).max() == pd.Timestamp("2026-07-31")

    failures = []
    x_end_mismatches = []
    for _, row in metrics.iterrows():
        candidate_id = str(row["candidate_id"])
        signal = live["candidate_signal_history"].loc[
            live["candidate_signal_history"]["candidate_id"].eq(candidate_id)
        ].copy()
        basis_date = pd.to_datetime(signal["date"]).max()
        fig = dash._macro5_kospi_build_main_chart(
            signal,
            live["benchmark_close_history"],
            dash._macro5_kospi_preset_label(row),
            5,
            False,
            basis_date=basis_date,
        )
        if fig is None:
            failures.append(candidate_id)
            continue
        if pd.to_datetime(fig.layout.xaxis.range[1]).normalize() != basis_date.normalize():
            x_end_mismatches.append(candidate_id)
        assert "KOSPI" in {trace.name for trace in fig.data}

    assert failures == []
    assert x_end_mismatches == []


def test_b3r_frozen_candidate_valid_signal_is_normalized_but_critical_missing_fails():
    live = _actual_page_data()
    history = live["candidate_signal_history"]
    frozen_rows = history.loc[pd.to_datetime(history["date"]) <= pd.Timestamp("2026-07-28")]
    live_rows = history.loc[pd.to_datetime(history["date"]) > pd.Timestamp("2026-07-28")]
    assert "valid_signal" in history.columns
    assert frozen_rows["valid_signal"].isna().sum() == 0
    assert frozen_rows["valid_signal"].astype(bool).all()
    assert live_rows["valid_signal"].isna().sum() == 0

    broken = history.loc[history["candidate_id"].eq(history["candidate_id"].iloc[0])].copy()
    broken.loc[broken.index[-1], "raw_risk_state"] = pd.NA
    fig = dash._macro5_kospi_build_main_chart(
        broken,
        live["benchmark_close_history"],
        "broken",
        5,
        False,
        basis_date=broken["date"].max(),
    )
    assert fig is None


def test_b3r_combo1_default_traces_are_not_raw_only_and_aux_adds_raw():
    live = _actual_page_data()
    assets = _assets()
    metrics = assets["metrics"]
    combo1 = metrics.loc[metrics["model_type"].eq("combo1")].iloc[0]
    parent_id = str(combo1["candidate_id"])
    component = live["component_signal_history"].loc[
        live["component_signal_history"]["parent_candidate_id"].eq(parent_id)
    ].copy()
    source_base = live["transformed_source_history"]
    benchmark = live["benchmark_close_history"]
    basis_date = live["candidate_signal_history"].loc[
        live["candidate_signal_history"]["candidate_id"].eq(parent_id), "date"
    ].max()

    for component_id, component_frame in component.groupby("component_id", sort=False):
        label = dash._macro5_kospi_component_display_label(str(component_id), _candidate_map(metrics), {})
        default_fig = dash._macro5_kospi_build_component_chart(
            component_frame,
            benchmark,
            label,
            5,
            model_type="combo1",
            source_base=source_base,
            show_aux=False,
            basis_date=basis_date,
        )
        assert default_fig is not None
        default_names = {trace.name for trace in default_fig.data}
        assert "KOSPI" in default_names
        assert "원자료" not in default_names
        assert (
            any(str(name).upper().startswith("EMA") for name in default_names)
            or "RSI" in default_names
            or "가격" in default_names
        )
        assert any(name in default_names for name in ["시작선", "상단 기준", "BB 상단"])
        assert any(name in default_names for name in ["종료선", "하단 기준", "BB 하단"])

        aux_fig = dash._macro5_kospi_build_component_chart(
            component_frame,
            benchmark,
            label,
            5,
            model_type="combo1",
            source_base=source_base,
            show_aux=True,
            basis_date=basis_date,
        )
        aux_names = {trace.name for trace in aux_fig.data}
        assert default_names.issubset(aux_names)


def test_b3r_ema_column_detection_covers_confirmed_spans():
    frame = pd.DataFrame(columns=["ema4", "ema10", "ema40", "ema80", "emaX", "xema10"])
    assert dash._macro5_kospi_ema_columns(frame) == ["ema4", "ema10", "ema40", "ema80"]


def test_b3r_combo2_children_have_no_binary_step_trace_and_no_hash_title():
    live = _actual_page_data()
    assets = _assets()
    metrics = assets["metrics"]
    combo2 = metrics.loc[metrics["model_type"].eq("combo2")].iloc[0]
    parent_id = str(combo2["candidate_id"])
    component = live["component_signal_history"].loc[
        live["component_signal_history"]["parent_candidate_id"].eq(parent_id)
    ].copy()
    benchmark = live["benchmark_close_history"]
    basis_date = live["candidate_signal_history"].loc[
        live["candidate_signal_history"]["candidate_id"].eq(parent_id), "date"
    ].max()

    for component_id, component_frame in component.groupby("component_id", sort=False):
        label = dash._macro5_kospi_component_display_label(str(component_id), _candidate_map(metrics), {})
        assert str(component_id) != label
        fig = dash._macro5_kospi_build_component_chart(
            component_frame,
            benchmark,
            label,
            5,
            model_type="combo2",
            source_base=live["transformed_source_history"],
            show_aux=False,
            basis_date=basis_date,
        )
        assert fig is not None
        names = {trace.name for trace in fig.data}
        shapes = {getattr(getattr(trace, "line", None), "shape", None) for trace in fig.data}
        assert "KOSPI" in names
        assert "Raw state" not in names
        assert "component ON" not in names
        assert "ON 수" not in names
        assert "K" not in names
        assert "L" not in names
        assert "hv" not in shapes
        assert len(fig.layout.annotations or []) >= 1
