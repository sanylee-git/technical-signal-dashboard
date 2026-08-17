from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_runtime import run_live_runtime
from kosdaq_macro7_runtime.presentation_payload import build_presentation_payload
from kosdaq_macro7_ui import (
    DEFAULT_CANDIDATE,
    _backtest_table,
    _component_chart,
    _component_display_label,
    _candidate_label,
    _component_status_table,
    _current_status_html,
    _group_summary,
    _main_chart,
    _snapshot_row,
    _stage,
)


def _fixture_frames():
    spec = importlib.util.spec_from_file_location("macro7_fixture", ROOT / "tests/test_kosdaq_macro7_d2_1_presentation_payload.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module._frames()


def _payload():
    live = run_live_runtime(as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), provider_frames=_fixture_frames())
    return build_presentation_payload(live)


def test_macro7_ui_uses_presentation_payload_without_kospi_runtime_dependency() -> None:
    source = (ROOT / "kosdaq_macro7_ui.py").read_text(encoding="utf-8")
    forbidden = ["kospi_macro5_runtime", "macro5_kospi", "yfinance", "requests", "fetch_all_sources"]
    for value in forbidden:
        assert value not in source
    assert "run_live_runtime" in source
    assert "build_presentation_payload" in source
    assert "macro7_kosdaq_preset" in source
    assert "presentation_only_ui_change_causing_runtime_refetch" not in source  # recorded in the Stage 4 contract/report, not calculated in UI.


def test_combo2_chart_only_uses_child_state_and_benchmark() -> None:
    payload = _payload()
    candidate_id = DEFAULT_CANDIDATE
    row = _snapshot_row(payload, candidate_id)
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(candidate_id)
    ].sort_values("component_order").iloc[0]
    assert component["component_kind"] == "CHILD_COMBO1_RAW_STATE"
    fig = _component_chart(payload, candidate_id, component["component_id"], component["component_kind"], row["basis_date"], 5)
    assert fig is not None
    assert [trace.name for trace in fig.data] == ["KOSDAQ"]


def test_combo1_chart_reads_chart_ready_core_fields_without_recomputation() -> None:
    payload = _payload()
    candidate_id = payload["final10"].loc[payload["final10"]["model_family"].eq("COMBO1"), "candidate_id"].iloc[0]
    row = _snapshot_row(payload, candidate_id)
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(candidate_id)
    ].sort_values("component_order").iloc[0]
    fig = _component_chart(payload, candidate_id, component["component_id"], component["component_kind"], row["basis_date"], 5, show_aux=True)
    assert fig is not None
    assert "Raw" in [trace.name for trace in fig.data]
    assert "KOSDAQ" in [trace.name for trace in fig.data]


def test_chart_ranges_and_default_candidate_are_bound_to_payload_basis_date() -> None:
    payload = _payload()
    row = _snapshot_row(payload, DEFAULT_CANDIDATE)
    fig = _main_chart(payload, DEFAULT_CANDIDATE, row["basis_date"], 5)
    assert fig is not None
    assert pd.Timestamp(fig.layout.xaxis.range[1]).normalize() == pd.Timestamp(row["basis_date"]).normalize()
    assert "조합1 5개/K3/L2" in fig.layout.title.text
    assert DEFAULT_CANDIDATE == "combo2_m5_k3_l2_50e15ab10d6cba46"


def test_all_period_charts_start_at_official_evaluation_boundary() -> None:
    payload = _payload()
    row = _snapshot_row(payload, DEFAULT_CANDIDATE)
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(DEFAULT_CANDIDATE)
    ].sort_values("component_order").iloc[0]

    main = _main_chart(payload, DEFAULT_CANDIDATE, row["basis_date"], "all")
    detail = _component_chart(payload, DEFAULT_CANDIDATE, component["component_id"], component["component_kind"], row["basis_date"], "all")
    expected_start = pd.Timestamp(payload["backtest_windows"]["evaluation_start"]).normalize()

    assert main is not None
    assert detail is not None
    assert pd.Timestamp(main.layout.xaxis.range[0]).normalize() == expected_start
    assert pd.Timestamp(detail.layout.xaxis.range[0]).normalize() == expected_start


def test_stage_display_is_only_a_label_projection() -> None:
    assert _stage(4, 4, 2, True) == "매도"
    assert _stage(1, 4, 2, False) == "매수심화"
    assert _stage(None, 4, 2, False) == "계산 불가"


def test_ui_contract_declares_no_presentation_state_refetch() -> None:
    contract = json.loads((ROOT / "kosdaq_macro7_assets/kosdaq_macro7_ui_contract.json").read_text(encoding="utf-8"))
    cache = contract["presentation_payload_cache"]
    assert cache["presentation_only_ui_change_causing_runtime_refetch"] == 0
    assert cache["payload_acquisition_per_page_render"] == 1
    assert cache["actual_run_live_runtime_cache_miss_max"] == 1


def test_kosdaq_summary_and_backtest_table_are_display_only_kospi_parity_elements() -> None:
    payload = _payload()

    summary = _group_summary(payload)
    table = _backtest_table(payload, "COMBO2", DEFAULT_CANDIDATE)

    assert "조합1+2" in summary
    assert "시장단계" in summary
    assert "KOSDAQ 홀드" in table
    assert "전체 자산" in table
    assert "전체 자산 (18Y)" in table
    assert "width:17.82%" in table
    for width in ("5.103%", "4.5%", "6.3%"):
        assert table.count(f"width:{width}") == 2
    assert "전체 CAGR" in table
    assert "x)</span>" in table
    assert table.index("KOSDAQ 홀드") < table.index("Main1 안정적 균형형") < table.index("Main2 성과 대표")


def test_kosdaq_component_labels_and_status_remain_payload_driven() -> None:
    payload = _payload()
    candidate_id = DEFAULT_CANDIDATE
    history = payload["candidate_history"].loc[
        payload["candidate_history"]["candidate_id"].eq(candidate_id)
    ]
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(candidate_id)
    ].sort_values("component_order").iloc[0]

    assert "구성 후보" in _component_display_label(component)
    status = _current_status_html(_snapshot_row(payload, candidate_id), history)
    assert "오늘 전환" in status
    assert "상태 구간 수익률" in status
    assert "최신 날짜" in _component_status_table(payload, candidate_id)


def test_kosdaq_main_labels_and_combo_family_separator_are_display_only() -> None:
    payload = _payload()
    rows = payload["final10"].set_index("candidate_id")

    assert "Main1 안정적 균형형" in _candidate_label(rows.loc["combo2_m5_k3_l2_50e15ab10d6cba46"])
    assert "Main2 성과 대표" in _candidate_label(rows.loc["combo2_m7_k4_l3_58c1eaea19e6d371"])
    assert "Main1 최고 성과형" in _candidate_label(rows.loc["combo1_n10_k8_l5_7d675fa2173be942"])
    assert "Main2 사이클·수익형" in _candidate_label(rows.loc["combo1_n9_k7_l5_ef47fc166183b7f0"])

    source = (ROOT / "kosdaq_macro7_ui.py").read_text(encoding="utf-8")
    assert "__macro7_kosdaq_combo1_separator__" in source
    assert "──────── 조합1 ────────" in source


def test_kosdaq_backtest_tables_render_before_main_chart() -> None:
    source = (ROOT / "kosdaq_macro7_ui.py").read_text(encoding="utf-8")
    assert source.index('with st.expander("백테스트 비교 보기 · 조합2"') < source.index("main = _main_chart(")


def test_kosdaq_ui_owns_macro5_visual_parity_styles_without_shared_runtime_import() -> None:
    source = (ROOT / "kosdaq_macro7_ui.py").read_text(encoding="utf-8")
    assert ".macro2-divider {border-top:1px solid rgba(255,255,255,0.08);margin:16px 0 24px}" in source
    assert ".macro2-helper-text {font-size:11.5px;line-height:1.45;color:rgba(255,255,255,0.56);margin:2px 0 14px 0}" in source
    assert "KOSDAQ 후보를 최신 데이터로 판단" not in source
    assert "kospi_macro5_runtime" not in source


def test_kosdaq_table_headers_follow_macro5_alignment_contract() -> None:
    payload = _payload()
    backtest = _backtest_table(payload, "COMBO2", DEFAULT_CANDIDATE)
    status = _component_status_table(payload, DEFAULT_CANDIDATE)

    assert "text-align:center;padding:6px 8px" in backtest
    assert "시장단계(1주 전)" in backtest
    assert "text-align:center;padding:6px 8px" in status
