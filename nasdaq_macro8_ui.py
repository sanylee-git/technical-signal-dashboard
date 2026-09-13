"""NASDAQ Macro8 presentation renderer backed by its independent Live runtime."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nasdaq_macro8_runtime.live_runtime import run_live_runtime
from nasdaq_macro8_runtime.presentation_payload import build_presentation_payload


RISK_ON = "#54F2A3"
RISK_OFF = "#FF8C69"
STAGE_COLORS = {
    "매수준비": RISK_OFF, "매수": "#22C55E", "매수심화": "#15803D",
    "홀드": RISK_ON, "관망": "#EA580C", "매도준비": "#A18707",
    "매도": "#F05A47", "매도심화": "#DC2626", "혼조": "#6B7280", "계산 불가": RISK_OFF,
}
STAGE_SCORES = {"매수심화": -3, "매수": -2, "매수준비": -1, "홀드": 0, "관망": 0, "매도준비": 1, "매도": 2, "매도심화": 3}
PERIOD_OPTIONS: list[int | str] = [2, 3, 5, 7, 10, 15, "all"]

# Operational labels/order are presentation-only. The frozen Final20 candidate
# definitions, component membership, and metrics remain unchanged.
NASDAQ_OPERATIONAL_ROLE_OVERRIDES = {
    "m5|n6|nq5e6_2c78a53ac6e928f8|n7|nq5e7_934189464a0ef2f2|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_d2cd70973210bf4d|n8|nq5e8_f2b2eadb0bc3f323|K3|L1": "Main1 균형형",
    "m8|n10|nq5e10_9bd42da1c1a6841b|n6|nq5e6_2c78a53ac6e928f8|n6|nq5e6_415194320e4754e5|n6|nq5e6_8b7fdbbd5d8db54a|n7|nq5e7_fc8f0fc4e97ae2e8|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L2": "Main2 고성과 Practical",
    "m6|n5|nq5e5_cb6d451a1c972e70|n6|nq5e6_8b7fdbbd5d8db54a|n7|nq5e7_07dba2edc2d519a1|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L1": "K/L 강건성",
    "n8|nq5e8_a6feb39063ce3ac4": "시대 안정성",
    "n8|nq5e8_6f60d9e268c12ef1": "Main1 Whipsaw / 방어",
    "n7|nq5e7_fc87283b72f8a856": "Main2 K/L 강건성",
}
NASDAQ_OPERATIONAL_DISPLAY_ORDER = {
    "m5|n6|nq5e6_2c78a53ac6e928f8|n7|nq5e7_934189464a0ef2f2|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_d2cd70973210bf4d|n8|nq5e8_f2b2eadb0bc3f323|K3|L1": 1,
    "m8|n10|nq5e10_9bd42da1c1a6841b|n6|nq5e6_2c78a53ac6e928f8|n6|nq5e6_415194320e4754e5|n6|nq5e6_8b7fdbbd5d8db54a|n7|nq5e7_fc8f0fc4e97ae2e8|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L2": 2,
    "m6|n5|nq5e5_cb6d451a1c972e70|n6|nq5e6_8b7fdbbd5d8db54a|n7|nq5e7_07dba2edc2d519a1|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L1": 3,
    "m7|n10|nq5e10_9bd42da1c1a6841b|n5|nq5e5_6194c950c7d8e169|n6|nq5e6_2c78a53ac6e928f8|n6|nq5e6_ec1d4faea1cff3e8|n7|nq5e7_2b2edceb8bbeb2b4|n8|nq5e8_f2b2eadb0bc3f323|n9|nq5e9_c796e1a7980688d2|K4|L2": 4,
    "m7|n10|nq5e10_c7dcb13d40794ed8|n12|nq5e12_10aa36a8dd29d82c|n12|nq5e12_6c99b08fcbf3f930|n6|nq5e6_18e02fabf8c4cfad|n6|nq5e6_cfe958901d9c70d4|n8|nq5e8_be766ae57cfa9042|n8|nq5e8_f2b2eadb0bc3f323|K4|L2": 5,
    "n8|nq5e8_6f60d9e268c12ef1": 1,
    "n7|nq5e7_fc87283b72f8a856": 2,
    "n8|nq5e8_a6feb39063ce3ac4": 3,
    "n8|nq5e8_8325c2bcedbdd951": 4,
    "n6|nq5e6_10b44c52f07a1b52": 5,
}


@st.cache_data(ttl=3600, show_spinner=False)
def _load_macro8_nasdaq_presentation_payload(live_sync_bucket: str) -> dict[str, Any]:
    """One NASDAQ-only Live acquisition per sync bucket; UI state is not a key."""
    del live_sync_bucket
    return build_presentation_payload(run_live_runtime())


def _live_sync_bucket(minutes: int = 60) -> str:
    return pd.Timestamp.now(tz="UTC").floor(f"{max(5, int(minutes))}min").strftime("%Y%m%d%H%M")


def _date(value: object) -> str:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "계산 불가"


def _fmt_pct(value: object, decimals: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_asset(value: object) -> str:
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return "-"


def _stage(active_count: object, k: object, l: object, risk_off: object) -> str:
    try:
        active, start_k, end_l = int(active_count), int(k), int(l)
    except (TypeError, ValueError):
        return "계산 불가"
    if active > start_k:
        return "매도심화"
    if active == start_k:
        return "매도"
    if active < end_l:
        return "매수심화"
    if active == end_l:
        return "매수"
    if not bool(risk_off) and active == start_k - 1:
        return "매도준비"
    if bool(risk_off) and active == end_l + 1:
        return "매수준비"
    return "관망" if bool(risk_off) else "홀드"


def _stage_html(label: str) -> str:
    return f"<span style='color:{STAGE_COLORS.get(label, '#AFAFAF')};font-weight:700'>{escape(label)}</span>"


def _on_k_html(active_count: object, k: object, risk_off: object) -> str:
    try:
        value = f"{max(0, int(active_count))}/K{max(1, int(k))}"
    except (TypeError, ValueError):
        return "계산 불가"
    return f"<span style='color:{RISK_OFF if bool(risk_off) else RISK_ON};font-weight:700'>{value}</span>"


def _candidate_label(row: pd.Series | dict[str, Any]) -> str:
    family = str(row.get("model_family", ""))
    prefix, unit = ("조합1", "지표") if family == "COMBO1" else ("조합2", "조합1")
    selection = "성과" if str(row.get("selection_type", "")) == "Performance" else "실전"
    return f"[{prefix} · {selection}] {row.get('display_role', '')} ({unit} {int(row.get('n_or_m', 0))}개/K{int(row.get('K', 0))}/L{int(row.get('L', 0))})"


def _ordered_candidate_ids(final: pd.DataFrame, family: str) -> list[str]:
    return final.loc[final["model_family"].eq(family)].sort_values("display_order")["candidate_id"].astype(str).tolist()


def _practical_final(final: pd.DataFrame) -> pd.DataFrame:
    """Return the fixed operational view without changing the Final20 contract."""
    out = final.loc[final["selection_type"].eq("Practical")].copy()
    counts = out["model_family"].value_counts()
    if len(out) != 10 or counts.get("COMBO1", 0) != 5 or counts.get("COMBO2", 0) != 5:
        raise RuntimeError("NASDAQ Macro8 Practical10 display contract failed")
    out["display_role"] = out.apply(
        lambda row: NASDAQ_OPERATIONAL_ROLE_OVERRIDES.get(str(row["candidate_id"]), str(row["display_role"])),
        axis=1,
    )
    out["display_order"] = out.apply(
        lambda row: NASDAQ_OPERATIONAL_DISPLAY_ORDER.get(str(row["candidate_id"]), int(row["display_order"])),
        axis=1,
    )
    return out.sort_values("display_order", kind="mergesort").reset_index(drop=True)


def _view(frame: pd.DataFrame, *, candidate_id: str | None = None, parent_id: str | None = None, start: object = None, end: object = None, years: int | str = "all") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    if candidate_id is not None and "candidate_id" in out:
        out = out.loc[out["candidate_id"].eq(candidate_id)]
    if parent_id is not None and "parent_candidate_id" in out:
        out = out.loc[out["parent_candidate_id"].eq(parent_id)]
    if start is not None:
        out = out.loc[out["date"].ge(pd.Timestamp(start).normalize())]
    if end is not None:
        out = out.loc[out["date"].le(pd.Timestamp(end).normalize())]
    if out.empty:
        return out
    out = out.sort_values("date", kind="mergesort")
    if years != "all":
        out = out.loc[out["date"].ge(out["date"].max() - pd.DateOffset(years=int(years)))]
    return out.reset_index(drop=True)


def _add_risk_background(fig: go.Figure, history: pd.DataFrame, state_column: str, x_end: pd.Timestamp) -> None:
    if history.empty or state_column not in history:
        return
    start: pd.Timestamp | None = None
    for row in history.itertuples(index=False):
        state = getattr(row, state_column)
        date = pd.Timestamp(row.date)
        if state == 1 and start is None:
            start = date
        elif state != 1 and start is not None:
            fig.add_vrect(x0=start, x1=date, fillcolor="rgba(183,62,74,0.18)", line_width=0, layer="below")
            start = None
    if start is not None:
        fig.add_vrect(x0=start, x1=x_end, fillcolor="rgba(183,62,74,0.18)", line_width=0, layer="below")


def _layout(fig: go.Figure, title: str, x_start: pd.Timestamp, x_end: pd.Timestamp) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=300, margin=dict(l=50, r=20, t=38, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text=title, font=dict(size=12, color="#9B9B9B"), x=0),
        font=dict(color="#C9C9C9"), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=1, xanchor="right", font=dict(size=10)),
    )
    fig.update_xaxes(range=[x_start, x_end], autorange=False, gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _display_start(payload: dict[str, Any], years: int | str) -> pd.Timestamp | None:
    return pd.Timestamp(payload["backtest_windows"]["evaluation_start"]) if years == "all" else None


def _main_chart(payload: dict[str, Any], candidate_id: str, basis: object, years: int | str) -> go.Figure | None:
    start = _display_start(payload, years)
    history = _view(payload["candidate_history"], candidate_id=candidate_id, start=start, end=basis, years=years)
    benchmark = _view(payload["benchmark_history"], candidate_id=candidate_id, start=start, end=basis, years=years)
    if history.empty or benchmark.empty:
        return None
    x_start, x_end = benchmark["date"].min(), pd.Timestamp(basis).normalize()
    fig = go.Figure()
    _add_risk_background(fig, history, "raw_risk_state", x_end)
    fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["ndx_close"], name="NASDAQ 100", line=dict(color="#BDBDBD", width=1.6)))
    for column, name, color, symbol in (("risk_start", "Risk 시작", "#F05A47", "triangle-down"), ("risk_end", "Risk 종료", "#60A5FA", "triangle-up")):
        events = history.loc[history[column].astype(bool)]
        if not events.empty:
            points = benchmark.merge(events[["date"]], on="date", how="inner")
            fig.add_trace(go.Scatter(x=points["date"], y=points["ndx_close"], name=name, mode="markers", marker=dict(color=color, size=10, symbol=symbol)))
    row = payload["final20"].loc[payload["final20"]["candidate_id"].eq(candidate_id)].iloc[0]
    return _layout(fig, _candidate_label(row), x_start, x_end)


def _component_chart(payload: dict[str, Any], parent_id: str, component_id: str, component_kind: str, basis: object, years: int | str, *, show_aux: bool) -> go.Figure | None:
    start = _display_start(payload, years)
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(parent_id)
        & payload["component_history"]["component_id"].eq(component_id)
    ]
    component = _view(component, start=start, end=basis, years=years)
    benchmark = _view(payload["benchmark_history"], candidate_id=parent_id, start=start, end=basis, years=years)
    if component.empty or benchmark.empty:
        return None
    x_start, x_end = benchmark["date"].min(), pd.Timestamp(basis).normalize()
    fig = go.Figure()
    _add_risk_background(fig, component, "component_risk_state", x_end)
    if component_kind == "CHILD_COMBO1_RAW_STATE":
        fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["ndx_close"], name="NASDAQ 100", line=dict(color="#BDBDBD", width=1.5)))
    else:
        chart = _view(payload["component_chart_history"], start=start, end=basis, years=years)
        chart = chart.loc[chart["component_id"].eq(component_id)]
        if chart.empty:
            return None
        fields = (("ema", "EMA", "#A78BFA"), ("start_line", "시작선", "#F05A47"), ("end_line", "종료선", "#60A5FA"))
        if show_aux:
            fields = (("value", "Raw", "#BDBDBD"),) + fields
        for column, label, color in fields:
            if column in chart and chart[column].notna().any():
                fig.add_trace(go.Scatter(x=chart["date"], y=chart[column], name=label, line=dict(color=color, width=1.25)))
        for column, label, color in (("lower", "하단", "#60A5FA"), ("upper", "상단", "#F05A47")):
            if column in chart and chart[column].notna().any():
                fig.add_trace(go.Scatter(x=chart["date"], y=chart[column], name=label, line=dict(color=color, width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["ndx_close"], name="NASDAQ 100", yaxis="y2", line=dict(color="#777777", width=1)))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, color="#808080"))
    label = str(component.iloc[-1]["component_label"])
    return _layout(fig, label, x_start, x_end)


def _snapshot_row(payload: dict[str, Any], candidate_id: str) -> pd.Series:
    return payload["snapshot"].loc[payload["snapshot"]["candidate_id"].eq(candidate_id)].iloc[0]


def _group_stage(labels: list[str]) -> str:
    if not labels or "계산 불가" in labels:
        return "계산 불가"
    # 혼조 is a valid aggregate result, not an unavailable calculation.
    # Combining a mixed group with another group must remain mixed.
    if "혼조" in labels:
        return "혼조"
    if any(label not in STAGE_SCORES for label in labels):
        return "계산 불가"
    scores = [STAGE_SCORES[label] for label in labels]
    buy, sell = sum(score < 0 for score in scores), sum(score > 0 for score in scores)
    if buy and sell:
        return "혼조"
    if not buy and not sell:
        return "홀드" if labels.count("홀드") >= labels.count("관망") else "관망"
    strength = sum(abs(score) for score in scores) / len(scores)
    if strength < 1.5:
        return "매수준비" if buy else "매도준비"
    if strength < 2.5:
        return "매수" if buy else "매도"
    return "매수심화" if buy else "매도심화"


def _stage_change_html(previous: str, current: str) -> str:
    return f"{_stage_html(previous)}<span style='color:rgba(255,255,255,.36);padding:0 4px'>→</span>{_stage_html(current)}"


def _group_summary(payload: dict[str, Any], final: pd.DataFrame | None = None) -> str:
    summary: dict[str, dict[str, str]] = {}
    snapshot = payload["snapshot"]
    final = _practical_final(payload["final20"]) if final is None else final
    for family, label in (("COMBO2", "조합2"), ("COMBO1", "조합1")):
        candidate_ids = final.loc[final["model_family"].eq(family), "candidate_id"]
        rows = snapshot.loc[snapshot["candidate_id"].isin(candidate_ids)]
        usable = rows.loc[rows["status"].eq("USABLE") & rows["availability_status"].ne("PROVISIONAL_UNAVAILABLE")]
        risk_off = int(usable["raw_risk_state"].astype(bool).sum())
        stage = [_stage(row.active_count, row.K, row.L, row.raw_risk_state) for row in usable.itertuples(index=False)]
        previous = [_stage(row.week_ago_active_count, row.K, row.L, row.week_ago_raw_risk_state) for row in usable.itertuples(index=False)]
        summary[label] = {
            "availability": f"<span style='color:{RISK_ON};font-weight:700'>{label} 계산 가능 {len(usable)} / {len(rows)}</span><span style='color:rgba(255,255,255,.55)'> · 계산 불가 {len(rows) - len(usable)}</span>",
            "risk": f"<span style='color:{RISK_OFF if risk_off else RISK_ON};font-weight:700'>{label} Risk-off(위험회피) {risk_off}/{len(rows)}</span><span style='color:rgba(255,255,255,.55)'> · 기준일 {_date(usable['basis_date'].max()) if not usable.empty else '계산 불가'}</span>",
            "stage": _group_stage(stage), "previous": _group_stage(previous),
        }
    separator = "<span style='color:rgba(255,255,255,.36);padding:0 10px'>|</span>"
    c2, c1 = summary["조합2"], summary["조합1"]
    combined_now = _group_stage([c1["stage"], c2["stage"]])
    combined_prev = _group_stage([c1["previous"], c2["previous"]])
    stages = f"<b>시장단계</b> · 조합1+2: {_stage_change_html(combined_prev, combined_now)}{separator}조합2: {_stage_change_html(c2['previous'], c2['stage'])}{separator}조합1: {_stage_change_html(c1['previous'], c1['stage'])}"
    return f"<div class='macro2-helper-text' style='margin-top:6px;line-height:1.55'><div>{c2['availability']}{separator}{c1['availability']}</div><div style='margin-top:2px'>{c2['risk']}{separator}{c1['risk']}</div><div style='margin-top:2px'>{stages}</div></div>"


def _signal_snapshot_html(label: str, row: pd.Series) -> str:
    if label == "잠정신호" and row.get("availability_status") == "PROVISIONAL_UNAVAILABLE":
        return "잠정신호: 계산 불가 (필수 원천 결측)"
    if row.get("status") != "USABLE":
        return f"{label}: 계산 불가"
    risk = bool(row["raw_risk_state"])
    color = RISK_OFF if risk else RISK_ON
    state = "Risk-off · 비투자" if risk else "Risk-on · 투자"
    return (
        f"{label}: 기준일 {_date(row['basis_date'])} <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"현재 플래그 {_on_k_html(row['active_count'], row['K'], risk)} <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"상태 <span style='color:{color};font-weight:700'>{state}</span>"
    )


def _current_status_html(
    row: pd.Series,
    history: pd.DataFrame,
    confirmed_row: pd.Series | None = None,
) -> str:
    if row.get("availability_status") == "PROVISIONAL_UNAVAILABLE":
        confirmed = row if confirmed_row is None else confirmed_row
        return (
            "<div class='macro2-helper-text' style='line-height:1.75'>"
            f"{_signal_snapshot_html('확정신호', confirmed)}<br>"
            "잠정신호: 확인 불가 (최신 라이브 원천을 준비하지 못함)<br>"
            "현재 상태: 최신 라이브 원천 확인 불가</div>"
        )
    if row["status"] != "USABLE":
        return "<div class='macro2-helper-text'>현재 상태를 계산할 수 없습니다.</div>"
    risk = bool(row["raw_risk_state"])
    color = RISK_OFF if risk else RISK_ON
    state = "Risk-off · 비투자" if risk else "Risk-on · 투자"
    segment = row.get("current_segment_return")
    segment_text = "확인 불가" if pd.isna(segment) else f"<span style='color:{RISK_ON if float(segment) >= 0 else RISK_OFF};font-weight:700'>{float(segment) * 100:.1f}%</span>"
    latest = history.sort_values("date").iloc[-1] if not history.empty else None
    if latest is None:
        transition = "오늘 전환 없음 · Risk-off 유지" if risk else "오늘 전환 없음 · Risk-on 유지"
    elif bool(latest.risk_start):
        transition = f"<span style='color:{RISK_OFF};font-weight:700'>오늘 전환: Risk-on → Risk-off · 방어 시작</span>"
    elif bool(latest.risk_end):
        transition = "<span style='color:#60A5FA;font-weight:700'>오늘 전환: Risk-off → Risk-on · 투자 재개</span>"
    else:
        transition = "오늘 전환 없음 · Risk-off 유지" if risk else "오늘 전환 없음 · Risk-on 유지"
    execution = "비투자" if int(row["invest_position"]) == 0 else "투자"
    confirmed_row = row if confirmed_row is None else confirmed_row
    provisional_date = pd.Timestamp(row["basis_date"]).normalize()
    confirmed_date = pd.Timestamp(confirmed_row["basis_date"]).normalize() if confirmed_row.get("basis_date") else None
    sessions = pd.to_datetime(history.get("date", pd.Series(dtype="datetime64[ns]")), errors="coerce").dropna().dt.normalize().drop_duplicates()
    gap = 0 if confirmed_date is None else int(((sessions > confirmed_date) & (sessions <= provisional_date)).sum())
    gap_html = "" if gap == 0 else f" <span style='color:rgba(255,255,255,.56)'>· 확정 기준과 {gap} 거래일 차이</span>"
    return (
        "<div class='macro2-helper-text' style='line-height:1.75'>"
        f"{_signal_snapshot_html('확정신호', confirmed_row)}<br>"
        f"{_signal_snapshot_html('잠정신호', row)}{gap_html}<br>"
        f"현재 상태 시작일 <span style='color:{color};font-weight:700'>{_date(row['current_risk_start_date'])}</span> <span style='color:rgba(255,255,255,.45)'>·</span> 지속 거래일 <span style='color:{color};font-weight:700'>{int(row['current_duration_trading_days'])}</span> <span style='color:rgba(255,255,255,.45)'>·</span> 상태 구간 수익률 {segment_text} <span style='color:rgba(255,255,255,.45)'>·</span> 실행 {execution} <span style='color:rgba(255,255,255,.45)'>·</span> {transition}</div>"
    )


def _metric_html(value: object, hold_value: object, formatter: Callable[[object], str], *, higher_is_better: bool) -> str:
    text = formatter(value)
    try:
        ratio = abs(float(value) / float(hold_value))
    except (TypeError, ValueError, ZeroDivisionError):
        return text
    if not np.isfinite(ratio):
        return text
    good = ratio > 1.0 if higher_is_better else ratio < 1.0
    return f"{text} <span style='color:{RISK_ON if good else '#8F8F8F'};font-size:11px;font-weight:{'700' if good else '400'}'>({ratio:.2f}x)</span>"


def _full_asset_header(windows: dict[str, Any]) -> str:
    years = int((pd.Timestamp(windows["frozen_cutoff"]) - pd.Timestamp(windows["evaluation_start"])).days / 365.25)
    return f"전체 자산 ({max(1, years)}Y)"


def _backtest_table(payload: dict[str, Any], family: str, selected_id: str, final: pd.DataFrame | None = None) -> str:
    final = _practical_final(payload["final20"]) if final is None else final
    final = final.loc[final["model_family"].eq(family)].sort_values("display_order")
    snapshot = payload["snapshot"].set_index("candidate_id")
    metrics = payload["frozen_display_metrics"]
    hold = payload["benchmark_display_metrics"].set_index("window")
    headers = ["역할 / 후보", "10Y 자산", _full_asset_header(payload["backtest_windows"]), "전체 CAGR", "10Y MDD", "전체 MDD", "전체 Risk-off", "전체 Cycle", "짧은 Cycle", "1주 전", "시장단계(1주 전)", "현재", "시장단계"]
    widths = ["12.3%", "5.3%", "5.3%", "4.5%", "5.0%", "5.0%", "4.5%", "3.7%", "3.7%", "3.2%", "4.6%", "3.2%", "4.6%"]
    colgroup = "<colgroup>" + "".join(f"<col style='width:{width}'>" for width in widths) + "</colgroup>"
    numeric = "padding:7px 8px;color:#D6D6D6;text-align:right;white-space:nowrap;"
    ten_hold, full_hold = hold.loc["10Y"], hold.loc["FULL"]
    rows = ["<tr>" + "".join([
        "<td style='padding:7px 8px;color:#EDEDED;font-weight:700;text-align:left;white-space:nowrap'>NASDAQ 100 홀드</td>",
        f"<td style='{numeric}'>{_fmt_asset(ten_hold.asset)}</td>", f"<td style='{numeric}'>{_fmt_asset(full_hold.asset)}</td>", f"<td style='{numeric}'>{_fmt_pct(full_hold.cagr)}</td>",
        f"<td style='{numeric}'>{_fmt_pct(ten_hold.mdd)}</td>", f"<td style='{numeric}'>{_fmt_pct(full_hold.mdd)}</td>", f"<td style='{numeric}'>{_fmt_pct(full_hold.risk_off_ratio)}</td>",
        "<td style='padding:7px 8px;text-align:center'>-</td>" * 6,
    ]) + "</tr>"]
    for _, candidate in final.iterrows():
        candidate_id = str(candidate.candidate_id)
        state = snapshot.loc[candidate_id]
        stats = metrics.loc[metrics["candidate_id"].eq(candidate_id)].set_index("window")
        ten, full = stats.loc["10Y"], stats.loc["FULL"]
        previous_stage = _stage(state.week_ago_active_count, state.K, state.L, state.week_ago_raw_risk_state)
        current_stage = _stage(state.active_count, state.K, state.L, state.raw_risk_state)
        selected = "background:rgba(120,126,231,.16);border-top:1px solid rgba(120,126,231,.34);border-bottom:1px solid rgba(120,126,231,.34);" if candidate_id == selected_id else ""
        cells = [
            f"<td title='{escape(_candidate_label(candidate))}' style='padding:7px 8px;color:#EDEDED;font-weight:700;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{escape(_candidate_label(candidate))}</td>",
            f"<td style='{numeric}'>{_metric_html(ten.asset, ten_hold.asset, _fmt_asset, higher_is_better=True)}</td>", f"<td style='{numeric}'>{_metric_html(full.asset, full_hold.asset, _fmt_asset, higher_is_better=True)}</td>", f"<td style='{numeric}'>{_metric_html(full.cagr, full_hold.cagr, _fmt_pct, higher_is_better=True)}</td>",
            f"<td style='{numeric}'>{_metric_html(ten.mdd, ten_hold.mdd, _fmt_pct, higher_is_better=False)}</td>", f"<td style='{numeric}'>{_metric_html(full.mdd, full_hold.mdd, _fmt_pct, higher_is_better=False)}</td>", f"<td style='{numeric}'>{_fmt_pct(full.risk_off_ratio)}</td>",
            f"<td style='{numeric}'>{int(full.completed_cycle_count)}</td>", f"<td style='{numeric}'>{int(full.short_cycle_20d_ratio * full.completed_cycle_count)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_on_k_html(state.week_ago_active_count, state.K, state.week_ago_raw_risk_state)}</td>", f"<td style='padding:7px 8px;text-align:center'>{_stage_html(previous_stage)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_on_k_html(state.active_count, state.K, state.raw_risk_state)}</td>", f"<td style='padding:7px 8px;text-align:center'>{_stage_html(current_stage)}</td>",
        ]
        rows.append(f"<tr style='{selected}'>" + "".join(cells) + "</tr>")
    alignments = ["left"] + ["right"] * 8 + ["center"] * 4
    head = "".join(f"<th style='text-align:{alignment};padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap'>{header}</th>" for header, alignment in zip(headers, alignments, strict=True))
    return f"<div class='macro-backtest-table-wrap' style='width:100%;overflow-x:auto'><table style='width:100%;min-width:1280px;table-layout:fixed;border-collapse:collapse;font-size:11px'>{colgroup}<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def _component_status_table(payload: dict[str, Any], candidate_id: str) -> str:
    history = _view(payload["component_history"], parent_id=candidate_id)
    if history.empty:
        return ""
    latest = history.sort_values("date").drop_duplicates("component_id", keep="last").sort_values("component_order")
    entries = []
    for row in latest.to_dict("records"):
        valid = bool(row.get("component_valid"))
        risk = bool(row.get("component_risk_state")) if valid else False
        flag = f"<span style='color:{RISK_OFF if risk else 'rgba(255,255,255,.18)'};font-weight:700'>●</span>"
        component_id = str(row.get("component_id"))
        provenance = payload.get("component_provenance_by_id", {})
        latest_text = provenance.get(component_id) or _date(row["date"])
        if component_id not in provenance:
            confirmed_basis = payload.get("component_confirmed_basis_by_id", {}).get(component_id)
            if latest_text and confirmed_basis and latest_text > str(confirmed_basis):
                latest_text = f"{latest_text} · 잠정 · 확정 {confirmed_basis}"
        entries.append((escape(str(row["component_label"])), flag, latest_text))
    midpoint = int(np.ceil(len(entries) / 2))
    body = []
    for index in range(max(midpoint, len(entries) - midpoint)):
        line = []
        for entry in (entries[:midpoint][index] if index < midpoint else None, entries[midpoint:][index] if index < len(entries) - midpoint else None):
            line.append("<td></td><td></td><td></td><td></td><td></td>" if entry is None else f"<td style='padding:5px 8px;color:#D6D6D6;vertical-align:top;overflow-wrap:anywhere'>{entry[0]}</td><td style='padding:5px 8px;text-align:center;color:#7C7CF7;vertical-align:top'>●</td><td style='padding:5px 8px;text-align:center;vertical-align:top'>{entry[1]}</td><td style='padding:5px 8px;color:#AFAFAF;vertical-align:top;overflow-wrap:anywhere'>{escape(str(entry[2] or '확인 불가'))}</td><td></td>")
        body.append("<tr>" + "".join(line) + "</tr>")
    header = "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>지표</th><th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>선택</th><th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>플래그</th><th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>최신 사용값</th><th style='border-bottom:1px solid rgba(255,255,255,.08)'></th>"
    return f"<table style='width:100%;border-collapse:collapse;font-size:11px;line-height:1.32'><thead><tr>{header}{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_css() -> None:
    st.markdown("""<style>
    .macro2-divider {border-top:1px solid rgba(255,255,255,0.08);margin:16px 0 24px}
    .macro2-divider-tight-top {margin:16px 0 24px}
    .macro2-helper-text {font-size:11.5px;line-height:1.45;color:rgba(255,255,255,0.56);margin:2px 0 14px 0}
    .macro2-control-label {font-size:11.5px;color:rgba(255,255,255,0.72);font-weight:600;line-height:1.2;margin-bottom:.7rem}
    .macro2-control-spacer {height:18px}
    .st-key-macro8_nasdaq_preset div[data-baseweb="select"] > div,.st-key-macro8_nasdaq_benchmark div[data-baseweb="select"] > div,.st-key-macro8_nasdaq_selected_components div[data-baseweb="select"] > div {min-height:2.55rem;border-color:rgba(95,86,214,.72)!important;background:rgba(52,44,112,.22)!important}
    .st-key-macro8_nasdaq_preset div[data-baseweb="select"] > div,.st-key-macro8_nasdaq_benchmark div[data-baseweb="select"] > div,.st-key-macro8_nasdaq_selected_components div[data-baseweb="select"] > div,.st-key-macro8_nasdaq_years div[data-baseweb="slider"] + div,.st-key-macro8_nasdaq_show_raw label,.st-key-macro8_nasdaq_show_raw span,.st-key-macro8_nasdaq_show_raw p {font-size:13.5px!important;color:rgba(255,255,255,.92)!important}
    .st-key-macro8_nasdaq_selected_components [data-baseweb="tag"] {background:rgba(92,79,214,.96)!important;color:#F6F4FF!important;min-height:24px!important;height:24px!important;padding:2px 8px!important;border-radius:6px!important;line-height:1.2!important;gap:4px!important;align-items:center!important}
    .st-key-macro8_nasdaq_selected_components [data-baseweb="tag"] span {font-size:11.5px!important;line-height:1.2!important}
    .st-key-macro8_nasdaq_show_raw [data-baseweb="checkbox"] > div {border-color:rgba(95,86,214,.78)!important}
    </style>""", unsafe_allow_html=True)


def render_macro8_nasdaq_section(container: Any, *, payload: dict[str, Any] | None = None, payload_loader: Callable[[str], dict[str, Any]] = _load_macro8_nasdaq_presentation_payload) -> None:
    """Render the fixed Practical10 view from one NASDAQ-only runtime payload."""
    with container:
        _render_css()
        if payload is None:
            try:
                payload = payload_loader(_live_sync_bucket())
            except Exception as exc:
                st.error(f"NASDAQ Macro8 Live 데이터를 준비하지 못했습니다: {exc}")
                return
        if not isinstance(payload, dict) or payload.get("ui_side_model_calculation_count") != 0:
            st.error("NASDAQ Macro8 presentation contract 검증 실패")
            return
        final = _practical_final(payload["final20"])
        combo2, combo1 = _ordered_candidate_ids(final, "COMBO2"), _ordered_candidate_ids(final, "COMBO1")
        ordered, separator = combo2 + combo1, "__macro8_nasdaq_combo1_separator__"
        default = combo2[0]
        if st.session_state.get("macro8_nasdaq_preset") == separator or st.session_state.get("macro8_nasdaq_preset") not in ordered:
            st.session_state["macro8_nasdaq_preset"] = default
        labels = {str(row.candidate_id): _candidate_label(row._asdict()) for row in final.itertuples(index=False)}
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        st.markdown(_group_summary(payload, final), unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
        for column, label in zip((c1, c2, c3, c4), ("조합 프리셋", "기준지수", "기간", "보조선 표시"), strict=True):
            with column:
                st.markdown(f'<div class="macro2-control-label">{label}</div>', unsafe_allow_html=True)
        st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
        with c1:
            candidate_id = st.selectbox("조합 프리셋", combo2 + [separator] + combo1, format_func=lambda value: "──────── 조합1 ────────" if value == separator else labels[value], key="macro8_nasdaq_preset", label_visibility="collapsed")
        if candidate_id == separator:
            candidate_id = combo1[0]
        state = _snapshot_row(payload, candidate_id)
        component_history = _view(payload["component_history"], parent_id=candidate_id, end=state.basis_date)
        options = [value for value in PERIOD_OPTIONS if value == "all" or (pd.Timestamp(state.basis_date) - component_history.date.min()).days >= int(value) * 365] or ["all"]
        with c2:
            st.selectbox("기준지수", ["NASDAQ 100"], key="macro8_nasdaq_benchmark", disabled=True, label_visibility="collapsed")
        with c3:
            period = st.select_slider("기간", options=options, value=5 if 5 in options else options[0], key="macro8_nasdaq_years", label_visibility="collapsed", format_func=lambda value: "전체" if value == "all" else f"{value}년")
        with c4:
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
            show_aux = st.checkbox("보조선 표시", value=False, key="macro8_nasdaq_show_raw", label_visibility="collapsed")
        components = component_history.sort_values("component_order")["component_id"].drop_duplicates().tolist()
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        controls, criteria = st.columns([4.4, 1.6], vertical_alignment="bottom")
        with controls:
            st.markdown('<div class="macro2-control-label">조합 지표</div>', unsafe_allow_html=True)
        with criteria:
            st.markdown('<div class="macro2-control-label">리스크 기준</div>', unsafe_allow_html=True)
        st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
        controls, criteria = st.columns([4.4, 1.6], vertical_alignment="top")
        with controls:
            st.multiselect("조합 지표", components, default=components, disabled=True, key="macro8_nasdaq_selected_components", label_visibility="collapsed", format_func=lambda component_id: str(component_history.loc[component_history["component_id"].eq(component_id)].iloc[0]["component_label"]))
        with criteria:
            st.markdown(f"<div style='padding-top:8px;font-size:11.5px;line-height:1.42;color:rgba(255,255,255,.84)'>시작 {int(state.K)}개 이상 ON<br>종료 {int(state.L)}개 이하 ON</div>", unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider macro2-divider-tight-top"></div>', unsafe_allow_html=True)
        candidate_history = _view(payload["candidate_history"], candidate_id=candidate_id, end=state.basis_date)
        confirmed_state = _snapshot_row({**payload, "snapshot": payload["confirmed_snapshot"]}, candidate_id)
        st.markdown(_current_status_html(state, candidate_history, confirmed_state), unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider macro2-divider-tight-top"></div>', unsafe_allow_html=True)
        with st.expander("백테스트 비교 보기 · 조합2", expanded=False):
            st.markdown(_backtest_table(payload, "COMBO2", candidate_id, final), unsafe_allow_html=True)
        with st.expander("백테스트 비교 보기 · 조합1", expanded=False):
            st.markdown(_backtest_table(payload, "COMBO1", candidate_id, final), unsafe_allow_html=True)
        with st.expander("지표별 상태 보기", expanded=False):
            st.markdown(_component_status_table(payload, candidate_id), unsafe_allow_html=True)
        with st.expander("데이터·Proxy 계약", expanded=False):
            st.markdown("<div class='macro2-helper-text'>Frozen Core15 기준선 + 최신 FRED/ Yahoo tail · FRED DBAA/DAAA/DGS10/DGS2/DGS3MO/DFII10/VIXCLS/VXVCLS/NFCI · ^NDX OHLC · ^NDXE Close<br><b>Proxy Only</b> · HY Proxy = DBAA − DGS10 · IG Proxy = DAAA − DGS10 · 직접 OAS 미사용</div>", unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        main = _main_chart(payload, candidate_id, state.basis_date, period)
        if main is None:
            st.warning("대표 차트 데이터를 준비하지 못했습니다.")
        else:
            st.plotly_chart(main, width="stretch", config={"displayModeBar": False}, key=f"macro8_nasdaq_main_chart_{candidate_id}_{period}")
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        for index, component_id in enumerate(components):
            row = component_history.loc[component_history["component_id"].eq(component_id)].iloc[-1]
            with st.expander(f"{index + 1}. {row.component_label}", expanded=True):
                chart = _component_chart(payload, candidate_id, component_id, str(row.component_kind), state.basis_date, period, show_aux=show_aux)
                if chart is None:
                    st.warning("상세 차트 필수 표시 필드가 없습니다.")
                else:
                    st.plotly_chart(chart, width="stretch", config={"displayModeBar": False}, key=f"macro8_nasdaq_component_chart_{candidate_id}_{index}_{period}")
        with st.expander("고급 설정 · 모델 및 데이터 정보", expanded=False):
            live = payload["live_metrics"].set_index("candidate_id").loc[candidate_id]
            st.write(f"candidate_id: `{candidate_id}`")
            st.write(f"공식 Frozen 백테스트: `2008-04-01 ~ {payload['backtest_windows']['frozen_cutoff']} · T+1 · 10bp · 현금수익 미적용`")
            st.write(f"CAGR: `{_fmt_pct(live.cagr)}` · MDD: `{_fmt_pct(live.mdd)}` · Calmar: `{float(live.calmar):.3f}`")
            st.write("Final20은 재선별하지 않으며, 화면에는 실전 후보 10개만 표시합니다. HY/IG는 전 기간 Proxy Only입니다.")
