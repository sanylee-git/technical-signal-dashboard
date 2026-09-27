"""Frozen visual review page for the three selected S&P2 Combo1 candidates."""

from __future__ import annotations

from html import escape
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from spx_macro9_trial_runtime import EXPECTED_IDS, load_trial_payload


RISK_OFF = "#F05A47"
RISK_ON = "#54F2A3"
EMA_YELLOW = "#F7C948"
START_ORANGE = "#FF8C69"
END_CYAN = "#78DCFF"
BENCHMARK_GRAY = "rgba(190,190,190,0.46)"
PERIODS: tuple[str, ...] = ("2년", "3년", "5년", "7년", "10년", "15년", "전체")
TIER_LABELS = {"T1_00_10": "Tier 1 · Short-cycle ≤10%", "T2_10_20": "Tier 2 · 10–20%", "T3_20_30": "Tier 3 · 20–30%"}


def _window(frame: pd.DataFrame, years: str, basis: pd.Timestamp) -> pd.DataFrame:
    out = frame.loc[frame.date.le(basis)].sort_values("date", kind="mergesort")
    if years != "전체" and not out.empty:
        out = out.loc[out.date.ge(basis - pd.DateOffset(years=int(years[:-1])))]
    return out.reset_index(drop=True)


def _risk_spans(frame: pd.DataFrame, state_column: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Build shaded intervals directly from one final state series."""
    if frame.empty:
        return []
    rows = frame.sort_values("date", kind="mergesort")
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    active_start: pd.Timestamp | None = None
    dates = pd.to_datetime(rows.date).dt.normalize().tolist()
    states = rows[state_column].astype(bool).tolist()
    for index, (date, risk_off) in enumerate(zip(dates, states, strict=True)):
        if risk_off and active_start is None:
            active_start = date
        elif not risk_off and active_start is not None:
            spans.append((active_start, date))
            active_start = None
        if index == len(dates) - 1 and active_start is not None:
            spans.append((active_start, date + pd.Timedelta(days=1)))
    return spans


def _add_shading(fig: go.Figure, frame: pd.DataFrame, state_column: str) -> None:
    for start, end in _risk_spans(frame, state_column):
        fig.add_vrect(x0=start, x1=end, fillcolor="rgba(183,62,74,0.18)", line_width=0, layer="below")


def _chart_layout(fig: go.Figure, title: str, height: int = 440) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=54, r=54, t=54, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#C9C9C9", size=11),
        title=dict(text=title, x=0, font=dict(size=13, color="#A9A9A9")),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right", font=dict(size=10)),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.045)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.045)", zeroline=False)
    return fig


def _candidate_chart(payload: dict[str, Any], candidate_id: str, years: str) -> go.Figure:
    row = payload["candidate_metrics"].loc[payload["candidate_metrics"].candidate_id.eq(candidate_id)].iloc[0]
    basis = pd.Timestamp(row.basis_date).normalize()
    history = _window(payload["candidate_history"].loc[payload["candidate_history"].candidate_id.eq(candidate_id)], years, basis)
    benchmark = _window(payload["benchmark_history"], years, basis)
    fig = go.Figure()
    _add_shading(fig, history, "strategy_risk_state")
    fig.add_trace(go.Scatter(x=benchmark.date, y=benchmark.close, name="S&P 500", line=dict(color="#BDBDBD", width=1.55)))
    for column, label, color, symbol in (
        ("risk_start", "Risk 시작", RISK_OFF, "triangle-down"),
        ("risk_end", "Risk 종료", "#60A5FA", "triangle-up"),
    ):
        events = history.loc[history[column].astype(bool), ["date"]]
        points = events.merge(benchmark[["date", "close"]], on="date", how="inner")
        if not points.empty:
            fig.add_trace(go.Scatter(x=points.date, y=points.close, name=label, mode="markers", marker=dict(color=color, size=9, symbol=symbol)))
    role = TIER_LABELS.get(str(row.short_tier), str(row.short_tier))
    return _chart_layout(fig, f"S&P 500 · {role} · N{int(row.n)}/K{int(row.K)}/L{int(row.L)}")


def _component_chart(payload: dict[str, Any], candidate_id: str, component_id: str, years: str, show_raw: bool) -> go.Figure:
    membership = payload["component_history"].loc[
        payload["component_history"].parent_candidate_id.eq(candidate_id)
        & payload["component_history"].component_id.eq(component_id)
    ].sort_values("date", kind="mergesort")
    chart = payload["component_chart_history"].loc[payload["component_chart_history"].component_id.eq(component_id)]
    basis = pd.Timestamp(chart.date.max()).normalize()
    membership = _window(membership, years, basis)
    chart = _window(chart, years, basis)
    fig = go.Figure()
    _add_shading(fig, membership, "component_risk_state")
    rsi_visible = "rsi" in chart and chart.rsi.notna().any()
    primary = "rsi" if rsi_visible else "ema"
    if show_raw and chart.value.notna().any():
        fig.add_trace(go.Scatter(x=chart.date, y=chart.value, name="Raw", line=dict(color="rgba(185,185,185,0.56)", width=1.0)))
    if rsi_visible:
        fig.add_trace(go.Scatter(x=chart.date, y=chart.rsi, name="RSI", line=dict(color=EMA_YELLOW, width=2.35)))
        for column, label, color in (("lower", "하한선", END_CYAN), ("upper", "상한선", START_ORANGE)):
            if chart[column].notna().any():
                fig.add_trace(go.Scatter(x=chart.date, y=chart[column], name=label, line=dict(color=color, width=2.0, dash="dot")))
    else:
        if chart.ema.notna().any():
            fig.add_trace(go.Scatter(x=chart.date, y=chart.ema, name="EMA", line=dict(color=EMA_YELLOW, width=2.35)))
        for column, label, color in (("start_line", "시작선", START_ORANGE), ("end_line", "종료선", END_CYAN)):
            if chart[column].notna().any():
                fig.add_trace(go.Scatter(x=chart.date, y=chart[column], name=label, line=dict(color=color, width=2.0, dash="dot")))

    marker_y = chart[primary]
    marker_data = chart.assign(_marker_y=marker_y)
    for column, label, color, symbol in (
        ("risk_start", "Risk 시작", RISK_OFF, "triangle-down"),
        ("risk_end", "Risk 종료", "#60A5FA", "triangle-up"),
    ):
        points = marker_data.loc[marker_data[column].astype(bool) & marker_data._marker_y.notna()]
        if not points.empty:
            fig.add_trace(go.Scatter(x=points.date, y=points["_marker_y"], name=label, mode="markers", marker=dict(color=color, size=8, symbol=symbol)))

    benchmark = payload["benchmark_history"].loc[payload["benchmark_history"].date.isin(chart.date)]
    fig.add_trace(go.Scatter(x=benchmark.date, y=benchmark.close, name="S&P 500", yaxis="y2", line=dict(color=BENCHMARK_GRAY, width=1.05)))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, color="#858585"))
    label = str(chart.component_label.iloc[0]) if not chart.empty else component_id
    return _chart_layout(fig, label, height=390)


def _candidate_label(row: pd.Series) -> str:
    tier = TIER_LABELS.get(str(row.short_tier), str(row.short_tier))
    return f"{tier} · N{int(row.n)}/K{int(row.K)}/L{int(row.L)} · {row.candidate_id}"


def _render_metrics_table(frame: pd.DataFrame, selected_id: str) -> None:
    view = frame[["display_order", "short_tier", "candidate_id", "n", "K", "L", "cagr", "mdd", "calmar", "raw_risk_off_cycle_count", "raw_short_cycle_20d_ratio", "raw_risk_state"]].copy()
    view.columns = ["순서", "Tier", "Candidate ID", "N", "K", "L", "CAGR", "MDD", "Calmar", "Risk-off Cycle", "Short Cycle ≤20일", "8/21 상태"]
    view["CAGR"] = view.CAGR.map(lambda value: f"{value:.1%}")
    view["MDD"] = view.MDD.map(lambda value: f"{value:.1%}")
    view["Calmar"] = view.Calmar.map(lambda value: f"{value:.2f}")
    view["Short Cycle ≤20일"] = frame.raw_short_cycle_20d_ratio.map(lambda value: f"{value:.1%}").to_numpy()
    view["8/21 상태"] = frame.raw_risk_state.map(lambda value: "Risk-off · 비투자" if int(value) else "Risk-on · 투자").to_numpy()
    st.dataframe(view, hide_index=True, width="stretch", height=165)
    st.caption(f"선택 모델: `{selected_id}`")


def render_snp2_combo1_trial_section(container: Any) -> None:
    with container:
        try:
            payload = load_trial_payload()
        except Exception as exc:
            st.error(f"S&P2 Frozen 미리보기 자산 검증 실패: {exc}")
            return
        if payload.get("ui_side_model_calculation_count") != 0:
            st.error("S&P2 미리보기는 사전 검증된 고정 자산만 표시해야 합니다.")
            return

        metrics = payload["candidate_metrics"].sort_values("display_order", kind="mergesort").reset_index(drop=True)
        st.markdown("### S&P2 · Combo1 후보 육안 검증")
        st.warning("Frozen 검증 화면입니다. 기준 데이터는 2008-04-01 ~ 2026-08-21이며, 2026-08-21 이후 Live 데이터는 포함하지 않습니다.")
        st.caption("표시 모델 3개 · Combo1만 · Combo2 없음 · 기존 SNP2 모델은 이 화면에 노출하지 않습니다.")
        _render_metrics_table(metrics, EXPECTED_IDS[0])

        c1, c2 = st.columns([2.2, 1.0], vertical_alignment="bottom")
        with c1:
            candidate_id = st.selectbox(
                "Combo1 후보",
                EXPECTED_IDS,
                index=0,
                format_func=lambda value: _candidate_label(metrics.loc[metrics.candidate_id.eq(value)].iloc[0]),
                key="spx2_trial_combo1_candidate",
            )
        with c2:
            years = st.select_slider("기간", options=list(PERIODS), value="5년", key="spx2_trial_combo1_period")
        selected = metrics.loc[metrics.candidate_id.eq(candidate_id)].iloc[0]
        state = int(selected.raw_risk_state)
        state_label = "Risk-off · 비투자" if state else "Risk-on · 투자"
        state_color = RISK_OFF if state else RISK_ON
        st.markdown(
            f"<div style='font-size:12px;line-height:1.8;color:#AFAFAF'>"
            f"기준일 <b>2026-08-21</b> · 현재 플래그 <b>{int(selected.active_count)}/{int(selected.K)}</b> · "
            f"상태 <span style='color:{state_color};font-weight:700'>{state_label}</span> · "
            f"Official T+1 1회 적용 · 추가 T+1 없음</div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(_candidate_chart(payload, candidate_id, years), width="stretch", config={"displaylogo": False})

        component_rows = payload["component_history"].loc[
            payload["component_history"].parent_candidate_id.eq(candidate_id)
        ].sort_values(["component_order", "date"], kind="mergesort")
        latest = component_rows.groupby("component_id", sort=False).tail(1).copy()
        latest["상태"] = latest.component_risk_state.map(lambda value: "Risk-off" if int(value) else "Risk-on")
        latest["유효"] = latest.component_valid.map(lambda value: "ON" if bool(value) else "OFF")
        status_view = latest[["component_order", "component_label", "component_id", "상태", "유효", "date"]].copy()
        status_view.columns = ["순서", "지표", "Component ID", "원시 상태", "유효값", "기준일"]
        status_view["기준일"] = pd.to_datetime(status_view["기준일"]).dt.strftime("%Y-%m-%d")
        st.dataframe(status_view, hide_index=True, width="stretch", height=min(430, 38 + len(status_view) * 35))

        components = component_rows[["component_order", "component_id", "component_label"]].drop_duplicates("component_id").sort_values("component_order")
        component_ids = components.component_id.astype(str).tolist()
        show_raw = st.checkbox("원자료 선 표시", value=False, key="spx2_trial_combo1_show_raw")
        for order, row in enumerate(components.itertuples(index=False)):
            with st.expander(f"{int(row.component_order)}. {row.component_label}", expanded=(order == 0)):
                st.caption(f"Component ID: `{row.component_id}`")
                st.plotly_chart(
                    _component_chart(payload, candidate_id, str(row.component_id), years, show_raw),
                    width="stretch",
                    config={"displaylogo": False},
                )

        with st.expander("검증 계약 / 입력 lineage", expanded=False):
            manifest = payload["manifest"]
            st.json({
                "status": manifest["status"],
                "mode": manifest["mode"],
                "period": manifest["evaluation_period"],
                "sessions": manifest["evaluation_sessions"],
                "candidates": manifest["candidates"],
                "source_runs": manifest["source_runs"],
                "qa": manifest["qa"],
                "inputs": {name: {"path": value["path"], "sha256": value["sha256"]} for name, value in manifest["inputs"].items()},
            })
