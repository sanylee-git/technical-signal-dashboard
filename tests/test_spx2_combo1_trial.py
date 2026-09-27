from __future__ import annotations

import pandas as pd

from spx_macro9_trial_ui import _candidate_chart, _component_chart, _risk_spans
from spx_macro9_trial_runtime import EXPECTED_IDS, load_trial_payload


def test_trial_payload_is_exactly_three_frozen_combo1_candidates():
    payload = load_trial_payload()
    metrics = payload["candidate_metrics"]
    assert tuple(metrics.candidate_id.astype(str)) == EXPECTED_IDS
    assert metrics.model_family.eq("COMBO1").all()
    assert len(metrics) == 3
    assert payload["manifest"]["combo2_count"] == 0
    assert payload["manifest"]["qa"]["candidate_official_t1_mismatch"] == 0
    assert payload["manifest"]["qa"]["component_transition_mismatch"] == 0
    assert payload["manifest"]["qa"]["additional_t1_application_count"] == 0


def test_candidate_chart_markers_follow_the_same_official_state_series():
    payload = load_trial_payload()
    candidate_id = EXPECTED_IDS[0]
    history = payload["candidate_history"].loc[
        payload["candidate_history"].candidate_id.eq(candidate_id)
    ].sort_values("date")
    fig = _candidate_chart(payload, candidate_id, "전체")
    traces = {trace.name: trace for trace in fig.data}
    for column, label in (("risk_start", "Risk 시작"), ("risk_end", "Risk 종료")):
        expected = history.loc[history[column].astype(bool), "date"].tolist()
        actual = list(pd.to_datetime(traces[label].x).normalize()) if label in traces else []
        assert actual == expected
    assert len(fig.layout.shapes) == len(_risk_spans(history, "strategy_risk_state"))


def test_rsi_component_chart_has_visible_rsi_and_dashed_thresholds():
    payload = load_trial_payload()
    candidate_id = EXPECTED_IDS[0]
    components = payload["component_history"].loc[
        payload["component_history"].parent_candidate_id.eq(candidate_id)
    ]
    rsi_id = components.loc[components.component_label.str.contains("RSI", case=False), "component_id"].iloc[0]
    fig = _component_chart(payload, candidate_id, str(rsi_id), "전체", False)
    traces = {trace.name: trace for trace in fig.data}
    assert "RSI" in traces
    assert "하한선" in traces and "상한선" in traces
    assert traces["하한선"].line.dash == "dot"
    assert traces["상한선"].line.dash == "dot"
    assert "S&P 500" in traces
