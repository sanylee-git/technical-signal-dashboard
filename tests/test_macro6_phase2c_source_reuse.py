import numpy as np
import pandas as pd

import technical_signal_dashboard as dash


def _spx_series() -> pd.Series:
    index = pd.bdate_range("2020-01-02", periods=320)
    return pd.Series(np.linspace(100.0, 140.0, len(index)), index=index)


def _level_cfg() -> dict:
    return {
        "kind": "level",
        "raw": "synthetic_vix",
        "ema": 1,
        "window": 40,
        "start": 0.8,
        "end": 0.2,
    }


def test_macro6_raw_source_cache_reuses_exact_same_request_within_combo2(monkeypatch) -> None:
    spx = _spx_series()
    calls = []

    def fake_raw_series(indicator, years, benchmark_name="S&P500", spx_s=None, sync_bucket=None):
        calls.append((indicator, years, benchmark_name, sync_bucket))
        index = pd.DatetimeIndex(spx_s.index)
        return pd.Series(np.sin(np.linspace(0.0, 8.0, len(index))) + 20.0, index=index)

    monkeypatch.setattr(dash, "_macro3_get_indicator_raw_series", fake_raw_series)
    component_cfg = {
        "selected_indicators": ["VIX"],
        "cfgs": {"VIX": _level_cfg()},
        "combo_k": 1,
        "combo_l": 0,
    }
    preset = {
        "kind": "combo2_final8",
        "components": ["child_a", "child_b"],
        "component_cfgs": {"child_a": component_cfg, "child_b": component_cfg},
        "combo_k": 1,
        "combo_l": 0,
    }

    combo, active = dash._compute_macro6_combo2_signal_frame(
        spx_s=spx,
        benchmark_name="S&P500",
        preset_cfg=preset,
        sync_bucket="bucket",
        raw_series_cache={},
    )

    assert not combo.empty
    assert active == ["child_a", "child_b"]
    assert calls == [("VIX", 4, "S&P500", "bucket")]


def test_macro6_raw_source_cache_matches_uncached_signal_and_separates_signature(monkeypatch) -> None:
    spx = _spx_series()
    calls = []

    def fake_raw_series(indicator, years, benchmark_name="S&P500", spx_s=None, sync_bucket=None):
        calls.append((indicator, years, benchmark_name, sync_bucket))
        index = pd.DatetimeIndex(spx_s.index)
        return pd.Series(np.linspace(float(years), float(years) + 1.0, len(index)), index=index)

    monkeypatch.setattr(dash, "_macro3_get_indicator_raw_series", fake_raw_series)
    cfg = _level_cfg()
    uncached = dash._macro6_get_indicator_signal_frame(
        indicator="VIX",
        cfg=cfg,
        benchmark_index=spx.index,
        years=4,
        benchmark_name="S&P500",
        spx_s=spx,
        sync_bucket="bucket",
        raw_series_cache=None,
    )
    cache = {}
    cached = dash._macro6_get_indicator_signal_frame(
        indicator="VIX",
        cfg=cfg,
        benchmark_index=spx.index,
        years=4,
        benchmark_name="S&P500",
        spx_s=spx,
        sync_bucket="bucket",
        raw_series_cache=cache,
    )
    cached_again = dash._macro6_get_indicator_signal_frame(
        indicator="VIX",
        cfg=cfg,
        benchmark_index=spx.index,
        years=4,
        benchmark_name="S&P500",
        spx_s=spx,
        sync_bucket="bucket",
        raw_series_cache=cache,
    )
    different_years = dash._macro6_get_indicator_signal_frame(
        indicator="VIX",
        cfg=cfg,
        benchmark_index=spx.index,
        years=5,
        benchmark_name="S&P500",
        spx_s=spx,
        sync_bucket="bucket",
        raw_series_cache=cache,
    )

    pd.testing.assert_frame_equal(cached, uncached)
    pd.testing.assert_frame_equal(cached_again, uncached)
    assert not different_years.empty
    assert calls == [
        ("VIX", 4, "S&P500", "bucket"),
        ("VIX", 4, "S&P500", "bucket"),
        ("VIX", 5, "S&P500", "bucket"),
    ]
