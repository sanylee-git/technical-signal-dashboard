import pandas as pd
import plotly.graph_objects as go

import technical_signal_dashboard as dash


def _spx():
    return pd.Series([100.0, 101.0, 102.0], index=pd.bdate_range("2026-01-01", periods=3))


def _cfg(raw="a"):
    return {
        "kind": "combo2_final8",
        "combo_k": 2,
        "combo_l": 1,
        "components": ["component_a"],
        "component_cfgs": {"component_a": {"raw": raw}},
    }


def _fig(name="chart"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4], name=name))
    fig.update_layout(title=name)
    return fig


def setup_function():
    dash._MACRO6_DETAIL_CHART_CACHE.clear()


def test_macro6_component_chart_cache_hits_same_contract(monkeypatch):
    calls = {"n": 0}

    def fake_builder(**_kwargs):
        calls["n"] += 1
        return _fig("component")

    monkeypatch.setattr(dash, "_build_macro6_component_chart", fake_builder)
    first = dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket")
    second = dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket")

    assert calls["n"] == 1
    assert first.to_json() == second.to_json()


def test_macro6_detail_chart_cache_returns_isolated_figures(monkeypatch):
    monkeypatch.setattr(dash, "_build_macro6_component_chart", lambda **_kwargs: _fig("component"))

    first = dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket")
    first.update_layout(title="mutated")
    second = dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket")

    assert second.layout.title.text == "component"


def test_macro6_detail_chart_cache_invalidates_scalar_contract_changes(monkeypatch):
    calls = {"n": 0}

    def fake_builder(**kwargs):
        calls["n"] += 1
        return _fig(f"component-{calls['n']}")

    monkeypatch.setattr(dash, "_build_macro6_component_chart", fake_builder)
    base = ("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket")
    dash._build_macro6_component_chart_cached(*base)
    dash._build_macro6_component_chart_cached("preset", "component_b", 5, "S&P500", _cfg(), _spx(), "bucket")
    dash._build_macro6_component_chart_cached("preset", "component_a", 7, "S&P500", _cfg(), _spx(), "bucket")
    dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg("changed"), _spx(), "bucket")
    dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "new_bucket")

    assert calls["n"] == 5


def test_macro6_indicator_chart_cache_includes_show_raw(monkeypatch):
    calls = {"n": 0}

    def fake_builder(**kwargs):
        calls["n"] += 1
        return _fig(f"indicator-{kwargs['show_raw']}")

    monkeypatch.setattr(dash, "_build_macro6_indicator_chart", fake_builder)
    dash._build_macro6_indicator_chart_cached("preset", "VIX", 5, "S&P500", _cfg(), _spx(), False, "bucket")
    dash._build_macro6_indicator_chart_cached("preset", "VIX", 5, "S&P500", _cfg(), _spx(), False, "bucket")
    dash._build_macro6_indicator_chart_cached("preset", "VIX", 5, "S&P500", _cfg(), _spx(), True, "bucket")

    assert calls["n"] == 2


def test_macro6_detail_chart_cache_does_not_store_none(monkeypatch):
    calls = {"n": 0}

    def fake_builder(**_kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr(dash, "_build_macro6_component_chart", fake_builder)
    assert dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket") is None
    assert dash._build_macro6_component_chart_cached("preset", "component_a", 5, "S&P500", _cfg(), _spx(), "bucket") is None

    assert calls["n"] == 2
    assert len(dash._MACRO6_DETAIL_CHART_CACHE) == 0
