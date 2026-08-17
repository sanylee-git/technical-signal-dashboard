"""KOSDAQ Macro7 presentation-only Streamlit renderer.

This module deliberately owns its market-specific UI namespace.  It consumes
the Stage 3.1 presentation payload as-is: no indicator, hysteresis, T+1, or
freshness calculation happens here.
"""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kosdaq_macro7_runtime.live_runtime import run_live_runtime
from kosdaq_macro7_runtime.presentation_payload import build_presentation_payload


RISK_ON = "#54F2A3"
RISK_OFF = "#FF8C69"
STAGE_COLORS = {
    "매수준비": RISK_ON, "매수": "#22C55E", "매수심화": "#15803D",
    "홀드": "#A18707", "관망": "#A18707", "매도준비": RISK_OFF,
    "매도": "#F05A47", "매도심화": "#DC2626", "혼조": "#6B7280", "계산 불가": RISK_OFF,
}
STAGE_SCORES = {
    "매수심화": -3, "매수": -2, "매수준비": -1, "홀드": 0,
    "관망": 0, "매도준비": 1, "매도": 2, "매도심화": 3,
}
PERIOD_OPTIONS: list[int | str] = [2, 3, 5, 7, 10, 15, "all"]
KOSDAQ_COMBO2_MAIN1 = "combo2_m5_k3_l2_50e15ab10d6cba46"
KOSDAQ_COMBO2_MAIN2 = "combo2_m7_k4_l3_58c1eaea19e6d371"
KOSDAQ_COMBO1_MAIN1 = "combo1_n10_k8_l5_7d675fa2173be942"
KOSDAQ_COMBO1_MAIN2 = "combo1_n9_k7_l5_ef47fc166183b7f0"
DEFAULT_CANDIDATE = KOSDAQ_COMBO2_MAIN1
KOSDAQ_DISPLAY_ROLE_OVERRIDES = {
    KOSDAQ_COMBO2_MAIN1: "Main1 안정적 균형형",
    KOSDAQ_COMBO2_MAIN2: "Main2 성과 대표",
    KOSDAQ_COMBO1_MAIN1: "Main1 최고 성과형",
    KOSDAQ_COMBO1_MAIN2: "Main2 사이클·수익형",
}


@st.cache_data(ttl=300, show_spinner=False)
def _load_macro7_kosdaq_presentation_payload(sync_bucket: str) -> dict[str, Any]:
    """One Macro7 runtime acquisition per cache miss; UI state is not a key."""
    del sync_bucket
    return build_presentation_payload(run_live_runtime())


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


def _date(value: object) -> str:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "계산 불가"


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
    return f"<span style='color:{STAGE_COLORS.get(label, '#AFAFAF')};font-weight:700;'>{escape(label)}</span>"


def _on_k_html(active_count: object, k: object, risk_off: object) -> str:
    try:
        label = f"{max(0, int(active_count))}/K{max(1, int(k))}"
    except (TypeError, ValueError):
        return "계산 불가"
    color = RISK_OFF if bool(risk_off) else RISK_ON
    return f"<span style='color:{color};font-weight:700;'>{label}</span>"


def _candidate_label(row: pd.Series | dict[str, Any]) -> str:
    family = str(row.get("model_family", ""))
    prefix = "조합1" if family == "COMBO1" else "조합2"
    unit = "지표" if family == "COMBO1" else "조합1"
    candidate_id = str(row.get("candidate_id") or (row.name if isinstance(row, pd.Series) else ""))
    role = KOSDAQ_DISPLAY_ROLE_OVERRIDES.get(candidate_id, str(row.get("display_role", "")))
    return f"[{prefix}] {role} ({unit} {int(row.get('n_or_m', 0))}개/K{int(row.get('K', 0))}/L{int(row.get('L', 0))})"


def _ordered_candidate_ids(final: pd.DataFrame, family: str) -> list[str]:
    candidate_ids = final.loc[final["model_family"].eq(family), "candidate_id"].tolist()
    preferred = (
        (KOSDAQ_COMBO2_MAIN1, KOSDAQ_COMBO2_MAIN2)
        if family == "COMBO2"
        else (KOSDAQ_COMBO1_MAIN1, KOSDAQ_COMBO1_MAIN2)
    )
    return [candidate_id for candidate_id in preferred if candidate_id in candidate_ids] + [candidate_id for candidate_id in candidate_ids if candidate_id not in preferred]


def _component_display_label(row: pd.Series | dict[str, Any]) -> str:
    """Return the frozen presentation label without inventing child roles."""
    return str(row.get("component_label", ""))


def _view(frame: pd.DataFrame, *, candidate_id: str | None = None, parent_id: str | None = None, start: object = None, end: object = None, years: int | str = "all") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    if candidate_id is not None and "candidate_id" in out:
        out = out.loc[out["candidate_id"].eq(candidate_id)]
    if parent_id is not None and "parent_candidate_id" in out:
        out = out.loc[out["parent_candidate_id"].eq(parent_id)]
    if end is not None:
        out = out.loc[out["date"].le(pd.Timestamp(end).normalize())]
    if start is not None:
        out = out.loc[out["date"].ge(pd.Timestamp(start).normalize())]
    if out.empty:
        return out
    out = out.sort_values("date")
    if years != "all":
        out = out.loc[out["date"].ge(out["date"].max() - pd.DateOffset(years=int(years)))]
    return out.reset_index(drop=True)


def _add_risk_background(fig: go.Figure, history: pd.DataFrame, state_column: str, x_end: pd.Timestamp) -> None:
    if history.empty or state_column not in history:
        return
    values = pd.to_numeric(history[state_column], errors="coerce")
    start: pd.Timestamp | None = None
    for row, state in zip(history.itertuples(index=False), values.fillna(-1), strict=False):
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
        legend=dict(orientation="h", y=1.01, x=1, xanchor="right", font=dict(size=10)),
    )
    fig.update_xaxes(range=[x_start, x_end], autorange=False, gridcolor="rgba(255,255,255,0.04)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
    return fig


def _chart_display_start(payload: dict[str, Any], years: int | str) -> pd.Timestamp | None:
    """Keep all-period charts within the official signal/backtest interval."""
    if years != "all":
        return None
    return pd.Timestamp(payload["backtest_windows"]["evaluation_start"]).normalize()


def _main_chart(payload: dict[str, Any], candidate_id: str, basis: object, years: int | str) -> go.Figure | None:
    display_start = _chart_display_start(payload, years)
    history = _view(payload["candidate_history"], candidate_id=candidate_id, start=display_start, end=basis, years=years)
    benchmark = _view(payload["benchmark_history"], candidate_id=candidate_id, start=display_start, end=basis, years=years)
    if history.empty or benchmark.empty:
        return None
    x_start, x_end = benchmark["date"].min(), pd.Timestamp(basis).normalize()
    fig = go.Figure()
    _add_risk_background(fig, history, "raw_risk_state", x_end)
    fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["kosdaq_close"], name="KOSDAQ", line=dict(color="#BDBDBD", width=1.6)))
    for column, name, color, symbol in (("risk_start", "Risk 시작", "#F05A47", "triangle-down"), ("risk_end", "Risk 종료", "#60A5FA", "triangle-up")):
        event = history.loc[history[column].astype(bool)] if column in history else history.iloc[0:0]
        if not event.empty:
            points = benchmark.merge(event[["date"]], on="date", how="inner")
            fig.add_trace(go.Scatter(x=points["date"], y=points["kosdaq_close"], name=name, mode="markers", marker=dict(color=color, size=10, symbol=symbol)))
    candidate = payload["final10"].loc[payload["final10"]["candidate_id"].eq(candidate_id)].iloc[0]
    return _layout(fig, _candidate_label(candidate), x_start, x_end)


def _component_chart(payload: dict[str, Any], parent_id: str, component_id: str, component_kind: str, basis: object, years: int | str, *, show_aux: bool = False) -> go.Figure | None:
    component = payload["component_history"].loc[
        payload["component_history"]["parent_candidate_id"].eq(parent_id)
        & payload["component_history"]["component_id"].eq(component_id)
    ]
    display_start = _chart_display_start(payload, years)
    component = _view(component, start=display_start, end=basis, years=years)
    benchmark = _view(payload["benchmark_history"], candidate_id=parent_id, start=display_start, end=basis, years=years)
    if component.empty or benchmark.empty:
        return None
    x_start, x_end = benchmark["date"].min(), pd.Timestamp(basis).normalize()
    fig = go.Figure()
    _add_risk_background(fig, component, "component_risk_state", x_end)
    # Combo2 children are complete Combo1 state histories.  No indicator
    # series is requested or synthesized for them.
    if component_kind == "CHILD_COMBO1_RAW_STATE":
        fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["kosdaq_close"], name="KOSDAQ", line=dict(color="#BDBDBD", width=1.5)))
    else:
        chart = _view(payload["component_chart_history"], start=display_start, end=basis, years=years)
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
        fig.add_trace(go.Scatter(x=benchmark["date"], y=benchmark["kosdaq_close"], name="KOSDAQ", yaxis="y2", line=dict(color="#777777", width=1)))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, color="#808080"))
    return _layout(fig, _component_display_label(component.iloc[-1]), x_start, x_end)


def _snapshot_row(payload: dict[str, Any], candidate_id: str) -> pd.Series:
    return payload["snapshot"].loc[payload["snapshot"]["candidate_id"].eq(candidate_id)].iloc[0]


def _group_stage(labels: list[str]) -> str:
    if not labels or any(label not in STAGE_SCORES for label in labels):
        return "계산 불가"
    scores = [STAGE_SCORES[label] for label in labels]
    buy, sell, neutral = sum(score < 0 for score in scores), sum(score > 0 for score in scores), sum(score == 0 for score in scores)
    neutral_label = "홀드" if labels.count("홀드") > labels.count("관망") else "관망" if labels.count("관망") > labels.count("홀드") else "혼조"
    if neutral > max(buy, sell):
        return neutral_label
    if buy and sell and max(buy, sell) / (buy + sell) < (2 / 3):
        return "혼조"
    if sell == buy:
        return "혼조"
    direction, dominant = ("SELL", [score for score in scores if score > 0]) if sell > buy else ("BUY", [score for score in scores if score < 0])
    strength = (sum(abs(score) for score in dominant) / len(dominant)) * (len(dominant) / len(scores))
    if strength < 0.5:
        return neutral_label
    if strength < 1.5:
        return "매도준비" if direction == "SELL" else "매수준비"
    if strength < 2.5:
        return "매도" if direction == "SELL" else "매수"
    return "매도심화" if direction == "SELL" else "매수심화"


def _combined_stage(combo1_stage: str, combo2_stage: str) -> str:
    stages = [combo1_stage, combo2_stage]
    if any(stage in {"계산 불가", "혼조"} for stage in stages):
        return "계산 불가" if "계산 불가" in stages else "혼조"
    scores = [STAGE_SCORES.get(stage) for stage in stages]
    if any(score is None for score in scores) or scores[0] * scores[1] < 0:
        return "혼조"
    if scores[0] == scores[1] == 0:
        return stages[0] if stages[0] == stages[1] else "혼조"
    score = sum(scores) / 2
    if abs(score) < 0.5:
        return "혼조"
    if abs(score) < 1.5:
        return "매도준비" if score > 0 else "매수준비"
    if abs(score) < 2.5:
        return "매도" if score > 0 else "매수"
    return "매도심화" if score > 0 else "매수심화"


def _stage_change_html(previous: str, current: str) -> str:
    arrow = "<span style='color:rgba(255,255,255,.36);padding:0 4px;'>→</span>"
    return f"{_stage_html(previous)}{arrow}{_stage_html(current)}"


def _group_summary(payload: dict[str, Any]) -> str:
    snapshot = payload["snapshot"]
    summary: dict[str, dict[str, str]] = {}
    for family, name in (("COMBO2", "조합2"), ("COMBO1", "조합1")):
        rows = snapshot.loc[snapshot["model_family"].eq(family)]
        usable = rows.loc[rows["status"].eq("USABLE")]
        risk_off = int(usable["raw_risk_state"].astype(bool).sum())
        basis = max((_date(value) for value in usable["basis_date"]), default="계산 불가")
        stages = [_stage(row.active_count, row.K, row.L, row.raw_risk_state) for row in usable.itertuples(index=False)]
        previous = [_stage(row.week_ago_active_count, row.K, row.L, row.week_ago_raw_risk_state) for row in usable.itertuples(index=False)]
        summary[name] = {
            "availability": f"<span style='color:{RISK_ON};font-weight:700'>{name} 계산 가능 {len(usable)} / {len(rows)}</span><span style='color:rgba(255,255,255,.55)'> · 계산 불가 {len(rows)-len(usable)}</span>",
            "risk": f"<span style='color:{RISK_OFF if risk_off else RISK_ON};font-weight:700'>{name} Risk-off(위험회피) {risk_off}/{len(rows)}</span><span style='color:rgba(255,255,255,.55)'> · 기준일 {basis}</span>",
            "stage": _group_stage(stages),
            "previous": _group_stage(previous),
        }
    separator = "<span style='color:rgba(255,255,255,.36);padding:0 10px;'>|</span>"
    combo2, combo1 = summary["조합2"], summary["조합1"]
    combined = _combined_stage(combo1["stage"], combo2["stage"])
    previous_combined = _combined_stage(combo1["previous"], combo2["previous"])
    stage_line = (
        f"<span><b>시장단계</b> · 조합1+2: {_stage_change_html(previous_combined, combined)}</span>{separator}"
        f"<span>조합2: {_stage_change_html(combo2['previous'], combo2['stage'])}</span>{separator}"
        f"<span>조합1: {_stage_change_html(combo1['previous'], combo1['stage'])}</span>"
    )
    return (
        "<div class='macro2-helper-text' style='margin-top:6px;line-height:1.55;'>"
        f"<div>{combo2['availability']}{separator}{combo1['availability']}</div>"
        f"<div style='margin-top:2px;'>{combo2['risk']}{separator}{combo1['risk']}</div>"
        f"<div style='margin-top:2px;'>{stage_line}</div></div>"
    )


def _today_transition_html(history: pd.DataFrame) -> str:
    if history.empty:
        return "오늘 전환 확인 불가"
    latest = history.sort_values("date").iloc[-1]
    if bool(latest.get("risk_start", False)):
        return f"<span style='color:{RISK_OFF};font-weight:700;'>오늘 Risk-off 시작</span>"
    if bool(latest.get("risk_end", False)):
        return "<span style='color:#60A5FA;font-weight:700;'>오늘 Risk-off 종료</span>"
    return "오늘 전환 없음"


def _current_status_html(row: pd.Series, candidate_history: pd.DataFrame) -> str:
    if row["status"] != "USABLE":
        return "<div class='macro2-helper-text'>현재 상태를 계산할 수 없습니다.</div>"
    state = bool(row["raw_risk_state"])
    color = RISK_OFF if state else RISK_ON
    state_text = "리스크 사이클 ON" if state else "리스크 사이클 OFF"
    execution = "비투자" if int(row["invest_position"]) == 0 else "투자"
    segment = row.get("current_segment_return")
    segment_html = "확인 불가" if pd.isna(segment) else f"<span style='color:{RISK_ON if float(segment) >= 0 else RISK_OFF};font-weight:700'>{float(segment)*100:.1f}%</span>"
    return (
        "<div class='macro2-helper-text' style='line-height:1.75;'>"
        f"기준일 {_date(row['basis_date'])} <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"현재 플래그 {_on_k_html(row['active_count'], row['K'], state)} <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"상태 <span style='color:{color};font-weight:700'>{state_text}</span><br>"
        f"현재 상태 시작일 <span style='color:{color};font-weight:700'>{_date(row['current_risk_start_date'])}</span> <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"지속 거래일 <span style='color:{color};font-weight:700'>{int(row['current_duration_trading_days'])}</span> <span style='color:rgba(255,255,255,.45)'>·</span> "
        f"상태 구간 수익률 {segment_html} <span style='color:rgba(255,255,255,.45)'>·</span> 실행 {execution} <span style='color:rgba(255,255,255,.45)'>·</span> {_today_transition_html(candidate_history)}</div>"
    )


def _metric_html(value: object, hold_value: object, formatter: Callable[[object], str], *, higher_is_better: bool) -> str:
    text = formatter(value)
    try:
        ratio = abs(float(value) / float(hold_value))
        if not np.isfinite(ratio):
            return text
    except (TypeError, ValueError, ZeroDivisionError):
        return text
    better = ratio > 1.0 if higher_is_better else ratio < 1.0
    color, weight = (RISK_ON, "700") if better else ("#8F8F8F", "400")
    return f"{text} <span style='color:{color};font-size:11px;font-weight:{weight};'>({ratio:.2f}x)</span>"


def _full_asset_header(backtest_windows: dict[str, Any]) -> str:
    try:
        start = pd.Timestamp(backtest_windows["evaluation_start"])
        end = pd.Timestamp(backtest_windows["frozen_cutoff"])
        years = int((end - start).days / 365.25)
    except (KeyError, TypeError, ValueError):
        return "전체 자산"
    return f"전체 자산 ({max(1, years)}Y)"


def _backtest_table(payload: dict[str, Any], family: str, selected_id: str) -> str:
    all_final = payload["final10"].sort_values(["model_family", "display_slot"])
    candidate_order = _ordered_candidate_ids(all_final, family)
    final = all_final.set_index("candidate_id").loc[candidate_order].reset_index()
    snapshot = payload["snapshot"].set_index("candidate_id")
    metrics = payload["frozen_display_metrics"]
    hold = payload["benchmark_display_metrics"].set_index("window")
    headers = ["역할 / 후보", "10Y 자산", _full_asset_header(payload["backtest_windows"]), "전체 CAGR", "10Y MDD", "전체 MDD", "전체 Risk-off", "전체 Cycle", "짧은 Cycle", "1주 전", "시장단계(1주 전)", "현재", "시장단계"]
    colgroup = "<colgroup>" + "".join(f"<col style='width:{width}'>" for width in ["16.929%", "7.271775%", "7.271775%", "6.23295%", "6.9255%", "6.9255%", "6.23295%", "5.103%", "5.103%", "4.05%", "5.67%", "4.05%", "5.67% "]) + "</colgroup>"
    style = "padding:7px 8px;color:#D6D6D6;text-align:right;white-space:nowrap;"
    rows = []
    ten_hold, full_hold = hold.loc["10Y"], hold.loc["FULL"]
    hold_cells = [
        "<td style='padding:7px 8px;color:#EDEDED;font-weight:700;text-align:left;white-space:nowrap'>KOSDAQ 홀드</td>",
        f"<td style='{style}'>{_fmt_asset(ten_hold.asset)}</td>", f"<td style='{style}'>{_fmt_asset(full_hold.asset)}</td>", f"<td style='{style}'>{_fmt_pct(full_hold.cagr)}</td>",
        f"<td style='{style}'>{_fmt_pct(ten_hold.mdd)}</td>", f"<td style='{style}'>{_fmt_pct(full_hold.mdd)}</td>", f"<td style='{style}'>{_fmt_pct(full_hold.risk_off_ratio)}</td>",
        "<td style='padding:7px 8px;text-align:center'>-</td>", "<td style='padding:7px 8px;text-align:center'>-</td>",
        "<td style='padding:7px 8px;text-align:center'>-</td>", "<td style='padding:7px 8px;text-align:center'>-</td>",
        "<td style='padding:7px 8px;text-align:center'>-</td>", "<td style='padding:7px 8px;text-align:center'>-</td>",
    ]
    rows.append("<tr>" + "".join(hold_cells) + "</tr>")
    for _, candidate in final.iterrows():
        cid = str(candidate["candidate_id"])
        state = snapshot.loc[cid]
        stats = metrics.loc[metrics["candidate_id"].eq(cid)].set_index("window")
        ten, full = stats.loc["10Y"], stats.loc["FULL"]
        week_stage = _stage(state["week_ago_active_count"], state["K"], state["L"], state["week_ago_raw_risk_state"])
        now_stage = _stage(state["active_count"], state["K"], state["L"], state["raw_risk_state"])
        selected_style = "background:rgba(120,126,231,.16);border-top:1px solid rgba(120,126,231,.34);border-bottom:1px solid rgba(120,126,231,.34);" if cid == selected_id else ""
        cells = [
            f"<td title='{escape(_candidate_label(candidate))}' style='padding:7px 8px;color:#EDEDED;font-weight:700;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{escape(_candidate_label(candidate))}</td>",
            f"<td style='{style}'>{_metric_html(ten.asset, ten_hold.asset, _fmt_asset, higher_is_better=True)}</td>", f"<td style='{style}'>{_metric_html(full.asset, full_hold.asset, _fmt_asset, higher_is_better=True)}</td>", f"<td style='{style}'>{_metric_html(full.cagr, full_hold.cagr, _fmt_pct, higher_is_better=True)}</td>",
            f"<td style='{style}'>{_metric_html(ten.mdd, ten_hold.mdd, _fmt_pct, higher_is_better=False)}</td>", f"<td style='{style}'>{_metric_html(full.mdd, full_hold.mdd, _fmt_pct, higher_is_better=False)}</td>", f"<td style='{style}'>{_fmt_pct(full.risk_off_ratio)}</td>",
            f"<td style='{style}'>{int(full.cycle)}</td>", f"<td style='{style}'>{int(full.short_cycle)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_on_k_html(state.week_ago_active_count, state.K, state.week_ago_raw_risk_state)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_stage_html(week_stage)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_on_k_html(state.active_count, state.K, state.raw_risk_state)}</td>",
            f"<td style='padding:7px 8px;text-align:center'>{_stage_html(now_stage)}</td>",
        ]
        rows.append(f"<tr style='{selected_style}'>" + "".join(cells) + "</tr>")
    alignments = ["left"] + ["right"] * 8 + ["center"] * 4
    return (
        "<div class='macro-backtest-table-wrap' style='width:100%;overflow-x:auto'><table style='width:100%;min-width:1406px;table-layout:fixed;border-collapse:collapse;font-size:11px'>"
        + colgroup + "<thead><tr>" + "".join(f"<th style='text-align:{alignment};padding:6px 8px;color:#8F8F8F;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap'>{header}</th>" for header, alignment in zip(headers, alignments, strict=True)) + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _component_status_table(payload: dict[str, Any], candidate_id: str) -> str:
    history = _view(payload["component_history"], parent_id=candidate_id)
    if history.empty:
        return ""
    latest = history.sort_values("date").drop_duplicates("component_id", keep="last").sort_values("component_order")
    entries = []
    for row in latest.to_dict("records"):
        valid = bool(row.get("component_valid"))
        state = bool(row.get("component_risk_state")) if valid else False
        flag = f"<span style='color:{RISK_OFF if state else 'rgba(255,255,255,.18)'};font-weight:700'>●</span>"
        entries.append((escape(_component_display_label(row)), flag, _date(row["date"])))
    midpoint = int(np.ceil(len(entries) / 2))
    left, right = entries[:midpoint], entries[midpoint:]
    body = []
    for index in range(max(len(left), len(right))):
        cells = []
        for entry in (left[index] if index < len(left) else None, right[index] if index < len(right) else None):
            if entry is None:
                cells.append("<td></td><td></td><td></td><td></td><td></td>")
            else:
                cells.append(f"<td style='padding:5px 8px;color:#D6D6D6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{entry[0]}</td><td style='padding:5px 8px;text-align:center;color:#7C7CF7'>●</td><td style='padding:5px 8px;text-align:center'>{entry[1]}</td><td style='padding:5px 8px;color:#AFAFAF;white-space:nowrap'>{entry[2]}</td><td></td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    header = "<th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>지표</th><th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>선택</th><th style='text-align:center;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08)'>플래그</th><th style='text-align:left;padding:6px 8px;color:#8F8F8F;font-weight:600;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap'>최신 날짜</th><th style='border-bottom:1px solid rgba(255,255,255,.08)'></th>"
    colgroup = "<colgroup><col style='width:27%'><col style='width:5%'><col style='width:5%'><col style='width:11%'><col style='width:2%'><col style='width:27%'><col style='width:5%'><col style='width:5%'><col style='width:11%'><col style='width:2%'></colgroup>"
    return f"<table style='width:100%;table-layout:fixed;border-collapse:collapse;font-size:11px'>{colgroup}<thead><tr>{header}{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_css() -> None:
    st.markdown("""
    <style>
    .macro2-divider {border-top:1px solid rgba(255,255,255,0.08);margin:16px 0 24px}
    .macro2-divider-tight-top {margin:16px 0 24px}
    .macro2-helper-text {font-size:11.5px;line-height:1.45;color:rgba(255,255,255,0.56);margin:2px 0 14px 0}
    .macro2-control-label {font-size:11.5px;color:rgba(255,255,255,0.72);font-weight:600;line-height:1.2;margin-bottom:.7rem}
    .macro2-control-spacer {height:18px}
    .st-key-macro7_kosdaq_preset div[data-baseweb="select"] > div,
    .st-key-macro7_kosdaq_benchmark div[data-baseweb="select"] > div,
    .st-key-macro7_kosdaq_selected_components div[data-baseweb="select"] > div {min-height:2.55rem;border-color:rgba(95,86,214,.72)!important;background:rgba(52,44,112,.22)!important}
    .st-key-macro7_kosdaq_preset div[data-baseweb="select"] > div,
    .st-key-macro7_kosdaq_benchmark div[data-baseweb="select"] > div,
    .st-key-macro7_kosdaq_selected_components div[data-baseweb="select"] > div,
    .st-key-macro7_kosdaq_years div[data-baseweb="slider"] + div,
    .st-key-macro7_kosdaq_show_raw label,
    .st-key-macro7_kosdaq_show_raw span,
    .st-key-macro7_kosdaq_show_raw p {font-size:13.5px!important;color:rgba(255,255,255,.92)!important}
    .st-key-macro7_kosdaq_selected_components [data-baseweb="tag"] {background:rgba(92,79,214,.96)!important;color:#F6F4FF!important;min-height:24px!important;height:24px!important;padding:2px 8px!important;border-radius:6px!important;line-height:1.2!important;gap:4px!important;align-items:center!important}
    .st-key-macro7_kosdaq_selected_components [data-baseweb="tag"] span {font-size:11.5px!important;line-height:1.2!important}
    .st-key-macro7_kosdaq_selected_components [data-baseweb="tag"] svg {width:12px!important;height:12px!important}
    .st-key-macro7_kosdaq_show_raw [data-baseweb="checkbox"] > div {border-color:rgba(95,86,214,.78)!important}
    .st-key-macro7_kosdaq_preset,.st-key-macro7_kosdaq_benchmark,.st-key-macro7_kosdaq_years,.st-key-macro7_kosdaq_show_raw,.st-key-macro7_kosdaq_selected_components {margin-top:0!important}
    </style>
    """, unsafe_allow_html=True)


def render_macro7_kosdaq_section(
    container: Any,
    *,
    payload: dict[str, Any] | None = None,
    payload_loader: Callable[[str], dict[str, Any]] = _load_macro7_kosdaq_presentation_payload,
    sync_bucket: str | None = None,
) -> None:
    """Render Macro7 using one already-computed presentation payload."""
    with container:
        _render_css()
        if payload is None:
            bucket = sync_bucket or pd.Timestamp.now(tz="UTC").strftime("%Y%m%d%H%M")
            try:
                payload = payload_loader(bucket)
            except Exception as exc:
                st.error(f"KOSDAQ Macro7 Live 데이터를 준비하지 못했습니다: {exc}")
                return
        if not isinstance(payload, dict) or payload.get("ui_side_model_calculation_count") != 0:
            st.error("KOSDAQ Macro7 presentation contract 검증 실패")
            return
        snapshot = payload["snapshot"].copy()
        final = payload["final10"].copy().sort_values(["model_family", "display_slot"])
        candidate_map = {str(row.candidate_id): row for row in final.itertuples(index=False)}
        combo2_order = _ordered_candidate_ids(final, "COMBO2")
        combo1_order = _ordered_candidate_ids(final, "COMBO1")
        ordered = combo2_order + combo1_order
        separator = "__macro7_kosdaq_combo1_separator__"
        if st.session_state.get("macro7_kosdaq_preset") == separator:
            st.session_state["macro7_kosdaq_preset"] = combo1_order[0] if combo1_order else DEFAULT_CANDIDATE
        if st.session_state.get("macro7_kosdaq_preset") not in ordered:
            st.session_state["macro7_kosdaq_preset"] = DEFAULT_CANDIDATE
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        st.markdown(_group_summary(payload), unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        labels = {cid: _candidate_label(candidate_map[cid]._asdict()) for cid in ordered}
        c1, c2, c3, c4 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
        for column, label in zip((c1, c2, c3, c4), ("조합 프리셋", "기준지수", "기간", "보조선 표시"), strict=True):
            with column:
                st.markdown(f'<div class="macro2-control-label">{label}</div>', unsafe_allow_html=True)
        st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1.8, 1.0, 2.2, 1.0], vertical_alignment="bottom")
        preset_options = combo2_order + [separator] + combo1_order
        with c1:
            candidate_id = st.selectbox(
                "조합 프리셋",
                preset_options,
                format_func=lambda value: "──────── 조합1 ────────" if value == separator else labels[value],
                key="macro7_kosdaq_preset",
                label_visibility="collapsed",
            )
        if candidate_id == separator:
            candidate_id = combo1_order[0] if combo1_order else DEFAULT_CANDIDATE
        state = _snapshot_row(payload, candidate_id)
        component_history = _view(payload["component_history"], parent_id=candidate_id, end=state["basis_date"])
        options = [option for option in PERIOD_OPTIONS if option == "all" or (pd.Timestamp(state["basis_date"]) - component_history["date"].min()).days >= int(option) * 365]
        if not options:
            options = ["all"]
        with c2:
            st.selectbox("기준지수", ["KOSDAQ"], key="macro7_kosdaq_benchmark", disabled=True, label_visibility="collapsed")
        with c3:
            period = st.select_slider("기간", options=options, value=5 if 5 in options else options[0], key="macro7_kosdaq_years", label_visibility="collapsed", format_func=lambda value: "전체" if value == "all" else f"{value}년")
        with c4:
            st.markdown('<div class="macro2-control-spacer"></div>', unsafe_allow_html=True)
            st.checkbox("보조선 표시", value=False, key="macro7_kosdaq_show_raw", label_visibility="collapsed")
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
            st.multiselect("조합 지표", components, default=components, disabled=True, key="macro7_kosdaq_selected_components", label_visibility="collapsed", format_func=lambda cid: _component_display_label(component_history.loc[component_history["component_id"].eq(cid)].iloc[0]))
        with criteria:
            st.markdown(
                f"<div style='padding-top:8px;font-size:11.5px;line-height:1.42;color:rgba(255,255,255,.84)'>시작 {int(state['K'])}개 이상 ON<br>종료 {int(state['L'])}개 이하 ON</div>",
                unsafe_allow_html=True,
            )
        st.markdown('<div class="macro2-divider macro2-divider-tight-top"></div>', unsafe_allow_html=True)
        candidate_history = _view(payload["candidate_history"], candidate_id=candidate_id, end=state["basis_date"])
        st.markdown(_current_status_html(state, candidate_history), unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider macro2-divider-tight-top"></div>', unsafe_allow_html=True)
        with st.expander("백테스트 비교 보기 · 조합2", expanded=False):
            st.markdown(_backtest_table(payload, "COMBO2", candidate_id), unsafe_allow_html=True)
        with st.expander("백테스트 비교 보기 · 조합1", expanded=False):
            st.markdown(_backtest_table(payload, "COMBO1", candidate_id), unsafe_allow_html=True)
        with st.expander("지표별 상태 보기", expanded=False):
            st.markdown(_component_status_table(payload, candidate_id), unsafe_allow_html=True)
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        main = _main_chart(payload, candidate_id, state["basis_date"], period)
        if main is None:
            st.warning("대표 차트 데이터를 준비하지 못했습니다.")
        else:
            st.plotly_chart(main, width="stretch", config={"displayModeBar": False}, key=f"macro7_kosdaq_main_chart_{candidate_id}_{period}")
        st.markdown('<div class="macro2-divider"></div>', unsafe_allow_html=True)
        for index, component_id in enumerate(components):
            row = component_history.loc[component_history["component_id"].eq(component_id)].iloc[-1]
            with st.expander(f"{index + 1}. {_component_display_label(row)}", expanded=True):
                fig = _component_chart(payload, candidate_id, component_id, str(row["component_kind"]), state["basis_date"], period, show_aux=bool(st.session_state["macro7_kosdaq_show_raw"]))
                if fig is None:
                    st.warning("상세 차트 필수 표시 필드가 없습니다.")
                else:
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"macro7_kosdaq_component_chart_{candidate_id}_{index}_{period}")
        with st.expander("고급 설정 · 모델 및 데이터 정보", expanded=False):
            st.write(f"candidate_id: `{candidate_id}`")
            st.write(f"slot: `{int(state['display_slot'])}`")
            st.write("공식 Frozen 백테스트: `2008-04-01 ~ 2026-07-28 · T+1 · 10bp · 현금수익 미적용`")
            st.write(f"CAGR: `{_fmt_pct(payload['live_metrics'].set_index('candidate_id').loc[candidate_id, 'CAGR'])}`")
            st.write(f"MDD: `{_fmt_pct(payload['live_metrics'].set_index('candidate_id').loc[candidate_id, 'MDD'])}`")
            st.write(f"Calmar: `{payload['live_metrics'].set_index('candidate_id').loc[candidate_id, 'Calmar']:.3f}`")
            st.write("Final10은 재선별하지 않습니다.")
