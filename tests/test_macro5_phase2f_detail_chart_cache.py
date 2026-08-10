import pandas as pd
import plotly.graph_objects as go

import technical_signal_dashboard as dash


def _component(component_id="component_a", parent="candidate_a", state_tail=1):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=4),
            "parent_candidate_id": [parent] * 4,
            "component_id": [component_id] * 4,
            "component_risk_state": [0, 1, 1, state_tail],
            "combo_risk_state": [0, 0, 1, 1],
            "valid_signal": [True] * 4,
        }
    )


def _benchmark():
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=4),
            "kospi_close": [2500.0, 2510.0, 2490.0, 2520.0],
        }
    )


def _source(extra_col=False):
    data = {
        "date": pd.bdate_range("2026-01-01", periods=4),
        "value": [1.0, 2.0, 3.0, 4.0],
    }
    if extra_col:
        data["extra"] = [0, 0, 0, 1]
    return pd.DataFrame(data)


def _fig(name="chart"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4], name=name))
    fig.update_layout(title=name)
    return fig


def setup_function():
    dash._MACRO5_KOSPI_DETAIL_CHART_CACHE.clear()


def test_macro5_combo1_component_chart_cache_hits_same_contract(monkeypatch):
    calls = {"n": 0}

    def fake_builder(*_args, **_kwargs):
        calls["n"] += 1
        return _fig("component")

    monkeypatch.setattr(dash, "_macro5_kospi_build_component_chart", fake_builder)
    first = dash._macro5_kospi_build_component_chart_cached(
        "candidate_a",
        _component(),
        _benchmark(),
        "Component A",
        5,
        model_type="combo1",
        source_base=_source(),
        show_aux=False,
        basis_date="2026-01-06",
        common_start="2026-01-01",
        live_sync_bucket="bucket",
    )
    second = dash._macro5_kospi_build_component_chart_cached(
        "candidate_a",
        _component(),
        _benchmark(),
        "Component A",
        5,
        model_type="combo1",
        source_base=_source(),
        show_aux=False,
        basis_date="2026-01-06",
        common_start="2026-01-01",
        live_sync_bucket="bucket",
    )

    assert calls["n"] == 1
    assert first.to_json() == second.to_json()


def test_macro5_combo2_component_chart_is_not_cached(monkeypatch):
    calls = {"n": 0}

    def fake_builder(*_args, **_kwargs):
        calls["n"] += 1
        return _fig("combo2")

    monkeypatch.setattr(dash, "_macro5_kospi_build_component_chart", fake_builder)
    for _ in range(2):
        dash._macro5_kospi_build_component_chart_cached(
            "candidate_combo2",
            _component(),
            _benchmark(),
            "Component A",
            5,
            model_type="combo2",
            source_base=_source(),
            show_aux=False,
            basis_date="2026-01-06",
            common_start="2026-01-01",
            live_sync_bucket="bucket",
        )

    assert calls["n"] == 2
    assert len(dash._MACRO5_KOSPI_DETAIL_CHART_CACHE) == 0


def test_macro5_component_chart_cache_returns_isolated_figures(monkeypatch):
    monkeypatch.setattr(dash, "_macro5_kospi_build_component_chart", lambda *_args, **_kwargs: _fig("component"))

    first = dash._macro5_kospi_build_component_chart_cached(
        "candidate_a", _component(), _benchmark(), "Component A", 5,
        model_type="combo1", source_base=_source(), basis_date="2026-01-06", common_start="2026-01-01", live_sync_bucket="bucket",
    )
    first.update_layout(title="mutated")
    second = dash._macro5_kospi_build_component_chart_cached(
        "candidate_a", _component(), _benchmark(), "Component A", 5,
        model_type="combo1", source_base=_source(), basis_date="2026-01-06", common_start="2026-01-01", live_sync_bucket="bucket",
    )

    assert second.layout.title.text == "component"


def test_macro5_component_chart_cache_invalidates_contract_changes(monkeypatch):
    calls = {"n": 0}

    def fake_builder(*_args, **_kwargs):
        calls["n"] += 1
        return _fig(f"component-{calls['n']}")

    monkeypatch.setattr(dash, "_macro5_kospi_build_component_chart", fake_builder)
    base_kwargs = {
        "model_type": "combo1",
        "source_base": _source(),
        "show_aux": False,
        "basis_date": "2026-01-06",
        "common_start": "2026-01-01",
        "live_sync_bucket": "bucket",
    }
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 5, **base_kwargs)
    dash._macro5_kospi_build_component_chart_cached("candidate_b", _component(parent="candidate_b"), _benchmark(), "Component A", 5, **base_kwargs)
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component("component_b"), _benchmark(), "Component B", 5, **base_kwargs)
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 7, **base_kwargs)
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 5, **{**base_kwargs, "show_aux": True})
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 5, **{**base_kwargs, "basis_date": "2026-01-07"})
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 5, **{**base_kwargs, "live_sync_bucket": "new_bucket"})
    dash._macro5_kospi_build_component_chart_cached("candidate_a", _component(), _benchmark(), "Component A", 5, **{**base_kwargs, "source_base": _source(extra_col=True)})

    assert calls["n"] == 8


def test_macro5_component_chart_cache_does_not_store_none(monkeypatch):
    calls = {"n": 0}

    def fake_builder(*_args, **_kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr(dash, "_macro5_kospi_build_component_chart", fake_builder)
    for _ in range(2):
        assert dash._macro5_kospi_build_component_chart_cached(
            "candidate_a",
            _component(),
            _benchmark(),
            "Component A",
            5,
            model_type="combo1",
            source_base=_source(),
            basis_date="2026-01-06",
            common_start="2026-01-01",
            live_sync_bucket="bucket",
        ) is None

    assert calls["n"] == 2
    assert len(dash._MACRO5_KOSPI_DETAIL_CHART_CACHE) == 0
