import pandas as pd

import technical_signal_dashboard as dash


def _sample_combo(index, state_tail=True):
    active_count = [0, 1, 2, 3, 4, 4, 3, 2]
    risk_state = [False, False, True, True, True, bool(state_tail), bool(state_tail), bool(state_tail)]
    combo = pd.DataFrame(
        {
            "credit_stress_flag": [False, True, True, True, True, True, True, False],
            "vix_flag": [False, False, True, True, True, True, False, False],
            "active_count": active_count,
            "combo_risk_state": risk_state,
            "combo_start_signal": [False, False, True, False, False, False, False, False],
            "combo_end_signal": [False, False, False, False, False, False, False, not state_tail],
        },
        index=index,
    )
    return combo


def test_macro6_summary_matches_full_state_payload(monkeypatch):
    index = pd.bdate_range("2026-01-01", periods=8)
    spx = pd.Series(range(100, 108), index=index, dtype=float)
    cfg = {
        "benchmark": "S&P500",
        "combo_k": 2,
        "combo_l": 1,
        "selected_indicators": ["Credit Stress", "VIX"],
        "cfgs": {
            "Credit Stress": {"raw": "a"},
            "VIX": {"raw": "b"},
        },
    }

    def fake_signal_frame(**_kwargs):
        return _sample_combo(index), ["Credit Stress", "VIX"]

    monkeypatch.setattr(dash, "_compute_macro6_preset_signal_frame", fake_signal_frame)
    full = dash._compute_macro6_operating_snapshot_uncached(cfg, sync_bucket="test", raw_series_cache={})
    summary = dash._compute_macro6_operating_summary(cfg, spx, "S&P500", sync_bucket="test", raw_series_cache={})

    for field in ["is_on", "on_count", "total_count", "start_count", "basis_date", "state_start_date", "state_duration_days"]:
        assert summary[field] == full[field]

    full_week_ago = dash._macro_week_ago_state_row(full["event_frame"])
    summary_week_ago = dash._macro_week_ago_state_row(summary["event_frame"])
    assert summary_week_ago["active_count"] == full_week_ago["active_count"]
    assert summary_week_ago["combo_risk_state"] == full_week_ago["combo_risk_state"]
    assert "combo_frame" not in summary
    assert set(summary["event_frame"].columns) == {"date", "active_count", "combo_risk_state"}


def test_macro6_group_helpers_accept_summary_without_combo_frame(monkeypatch):
    index = pd.bdate_range("2026-01-01", periods=8)
    spx = pd.Series(range(100, 108), index=index, dtype=float)
    preset_defs = {
        "p1": {"label": "P1", "benchmark": "S&P500", "combo_k": 2, "combo_l": 1, "selected_indicators": ["Credit Stress"], "cfgs": {"Credit Stress": {"raw": "a"}}},
        "p2": {"label": "P2", "benchmark": "S&P500", "combo_k": 2, "combo_l": 1, "selected_indicators": ["VIX"], "cfgs": {"VIX": {"raw": "b"}}},
    }

    def fake_signal_frame(**kwargs):
        tail = kwargs["preset_cfg"].get("label") == "P1"
        return _sample_combo(index, state_tail=tail), ["Credit Stress", "VIX"]

    monkeypatch.setattr(dash, "_compute_macro6_preset_signal_frame", fake_signal_frame)
    summary_map = {
        key: dash._compute_macro6_operating_summary(cfg, spx, "S&P500", sync_bucket="test", raw_series_cache={})
        for key, cfg in preset_defs.items()
    }

    consensus = dash._macro6_group_consensus_html(
        "조합",
        ("p1", "p2"),
        preset_defs,
        {"p1": [], "p2": []},
        years=5,
        sync_bucket="test",
        snapshot_map=summary_map,
    )
    current_stage = dash._macro6_group_market_stage_label(
        ("p1", "p2"),
        preset_defs,
        {"p1": [], "p2": []},
        snapshot_map=summary_map,
    )
    week_ago_stage = dash._macro6_group_market_stage_label(
        ("p1", "p2"),
        preset_defs,
        {"p1": [], "p2": []},
        snapshot_map=summary_map,
        use_week_ago=True,
    )

    assert "Risk-off(위험회피) 1/2" in consensus
    assert current_stage != "계산 불가"
    assert week_ago_stage != "계산 불가"


def test_macro6_selected_snapshot_reuses_exact_summary_signal(monkeypatch):
    dash._MACRO6_SELECTED_SIGNAL_REUSE_STORE.clear()
    index = pd.bdate_range("2024-01-01", periods=8)
    spx = pd.Series(range(100, 108), index=index, dtype=float)
    cfg = {
        "candidate_key": "candidate_a",
        "benchmark": "S&P500",
        "combo_k": 2,
        "combo_l": 1,
        "selected_indicators": ["Credit Stress", "VIX"],
        "cfgs": {
            "Credit Stress": {"raw": "a"},
            "VIX": {"raw": "b"},
        },
    }
    calls = {"signal": 0}

    def fake_signal_frame(**_kwargs):
        calls["signal"] += 1
        return _sample_combo(index), ["Credit Stress", "VIX"]

    monkeypatch.setattr(dash, "_yf_close", lambda *_args, **_kwargs: spx)
    monkeypatch.setattr(dash, "_compute_macro6_preset_signal_frame", fake_signal_frame)
    summary = dash._compute_macro6_operating_summary(
        cfg,
        spx,
        "S&P500",
        sync_bucket="bucket",
        raw_series_cache={},
        reuse_capture_key="candidate_a",
    )
    full = dash._compute_macro6_operating_snapshot_uncached(cfg, sync_bucket="bucket")

    assert calls["signal"] == 1
    for field in ["is_on", "on_count", "total_count", "start_count", "basis_date", "state_start_date", "state_duration_days"]:
        assert summary[field] == full[field]
    assert "combo_frame" not in summary
    assert "combo_frame" in full
    dash._MACRO6_SELECTED_SIGNAL_REUSE_STORE.clear()


def test_macro6_selected_snapshot_falls_back_on_identity_mismatch(monkeypatch):
    dash._MACRO6_SELECTED_SIGNAL_REUSE_STORE.clear()
    index = pd.bdate_range("2024-01-01", periods=8)
    spx = pd.Series(range(100, 108), index=index, dtype=float)
    cfg = {
        "candidate_key": "candidate_a",
        "benchmark": "S&P500",
        "combo_k": 2,
        "combo_l": 1,
        "selected_indicators": ["Credit Stress", "VIX"],
        "cfgs": {
            "Credit Stress": {"raw": "a"},
            "VIX": {"raw": "b"},
        },
    }
    mismatch_cfg = {**cfg, "combo_k": 3}
    calls = {"signal": 0}

    def fake_signal_frame(**_kwargs):
        calls["signal"] += 1
        return _sample_combo(index), ["Credit Stress", "VIX"]

    monkeypatch.setattr(dash, "_yf_close", lambda *_args, **_kwargs: spx)
    monkeypatch.setattr(dash, "_compute_macro6_preset_signal_frame", fake_signal_frame)
    dash._compute_macro6_operating_summary(
        cfg,
        spx,
        "S&P500",
        sync_bucket="bucket",
        raw_series_cache={},
        reuse_capture_key="candidate_a",
    )
    full = dash._compute_macro6_operating_snapshot_uncached(mismatch_cfg, sync_bucket="bucket")

    assert calls["signal"] == 2
    assert full is not None
    dash._MACRO6_SELECTED_SIGNAL_REUSE_STORE.clear()


def test_macro6_component_chart_and_status_paths_remain_separate(monkeypatch):
    index = pd.bdate_range("2024-01-01", periods=8)
    spx = pd.Series(range(100, 108), index=index, dtype=float)
    combo = _sample_combo(index)
    component_key = "combo1_component"
    component_cfg = {
        "combo_k": 2,
        "combo_l": 1,
        "selected_indicators": ["Credit Stress", "VIX"],
        "cfgs": {
            "Credit Stress": {"raw": "a"},
            "VIX": {"raw": "b"},
        },
    }
    preset_cfg = {
        "kind": "combo2_final8",
        "combo_k": 1,
        "combo_l": 0,
        "components": [component_key],
        "component_cfgs": {component_key: component_cfg},
    }
    calls = {"chart_signal": 0, "status": 0}

    def fake_combo_signal(**_kwargs):
        calls["chart_signal"] += 1
        return combo, ["Credit Stress", "VIX"]

    def fake_component_status(*_args, **_kwargs):
        calls["status"] += 1
        return {
            "rows": [],
            "bottleneck": {"label": "Credit Stress", "latest_text": "2024-01-10"},
        }

    event_df = dash._macro6_build_event_df(combo, [component_key], "S&P500", preset_cfg)
    monkeypatch.setattr(dash, "_yf_close", lambda *_args, **_kwargs: spx)
    monkeypatch.setattr(dash, "_compute_macro6_combo_signal_frame", fake_combo_signal)
    monkeypatch.setattr(dash, "_macro6_component_data_status", fake_component_status)

    fig = dash._build_macro6_component_chart(
        component_key=component_key,
        years=5,
        benchmark_name="S&P500",
        preset_cfg=preset_cfg,
        spx_s=spx,
        sync_bucket="bucket",
    )
    status_html, status_table = dash._build_macro6_status_panel(
        benchmark_name="S&P500",
        years=5,
        preset_cfg=preset_cfg,
        combo_event_df=event_df,
        sync_bucket="bucket",
    )

    assert fig is not None
    assert status_html
    assert status_table
    assert calls["chart_signal"] == 1
    assert calls["status"] == 1
