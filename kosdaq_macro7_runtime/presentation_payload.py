"""UI-ready Macro7 data built from an already-calculated Live runtime payload.

This module intentionally has no Streamlit, cache, or network dependency.  It
does not choose candidates or change model state; it only exposes the exact
history and display fields a page needs to render the locked Final10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import (
    INITIAL_CAPITAL,
    _align,
    _bollinger,
    _dynamic_level,
    _rsi,
    _wilder_atr,
)


ASSETS = Path(__file__).resolve().parents[1] / "kosdaq_macro7_assets"
FROZEN_CUTOFF = pd.Timestamp("2026-07-28")
EVALUATION_START = "2008-04-01"


def _date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _frame_with_date(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    return result.sort_values("date").reset_index(drop=True)


def _final_and_definitions() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    final = pd.read_csv(ASSETS / "kosdaq_macro7_final10.csv").sort_values(["model_family", "display_slot"])
    definitions = pd.read_csv(ASSETS / "kosdaq_macro7_signal_definitions.csv")
    children = pd.read_csv(ASSETS / "kosdaq_macro7_combo2_child_mapping.csv")
    return final.reset_index(drop=True), definitions.reset_index(drop=True), children.reset_index(drop=True)


def _required_core_ids(final: pd.DataFrame, children: pd.DataFrame) -> set[str]:
    core_ids: set[str] = set()
    for row in final.loc[final["model_family"].eq("COMBO1")].itertuples(index=False):
        core_ids.update(str(row.candidate_ids).split("|"))
    for row in children.itertuples(index=False):
        core_ids.update(str(row.child_candidate_ids).split("|"))
    return core_ids


def _detail_signal(frame: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    """Use the pinned Frozen Replay primitives to expose chart-only series."""
    params = json.loads(row.params_json)
    indicator = str(row.indicator_id)
    kind = str(row.kind)
    if kind == "rsi":
        return _rsi(frame["kosdaq_close"], params)
    if kind == "bollinger":
        return _bollinger(frame, params)
    if kind == "yield_slope":
        window = int(params["slope_window"])
        values = pd.to_numeric(frame["us_10y_yield"], errors="coerce")
        x = np.arange(window, dtype=float)
        centered = x - x.mean()
        denominator = float(np.dot(centered, centered))
        slope = values.rolling(window, min_periods=window).apply(
            lambda series: np.nan if np.isnan(series).any() else float(np.dot(centered, series) / denominator),
            raw=True,
        )
        return _dynamic_level(
            -slope,
            {
                "ema_span": params["ema_span"],
                "window": params["threshold_window"],
                "start_q": params["start_q"],
                "end_q": params["end_q"],
            },
        )
    if indicator == "kosdaq_natr":
        value = -(100.0 * _wilder_atr(frame, int(params["natr_n"])) / pd.to_numeric(frame["kosdaq_close"], errors="coerce"))
        eligible = frame["kosdaq_ohlc_signal_eligible"].astype(bool)
        return _dynamic_level(value, params, eligible & eligible.shift(1, fill_value=False))
    if indicator == "kosdaq_hv":
        close = pd.to_numeric(frame["kosdaq_close"], errors="coerce").where(lambda series: series > 0)
        value = -(np.log(close / close.shift(1)).rolling(int(params["hv_n"]), min_periods=int(params["hv_n"])).std(ddof=1) * np.sqrt(252.0))
        return _dynamic_level(value, params)
    return _dynamic_level(frame[str(row.source_column)], params)


def _core_chart_history(live_payload: dict[str, Any], definitions: pd.DataFrame, required_ids: set[str]) -> pd.DataFrame:
    combined = _frame_with_date(live_payload["combined"]).set_index("date")
    core = _frame_with_date(live_payload["core"])
    calendar = combined.index
    parts: list[pd.DataFrame] = []
    for row in definitions.loc[definitions["candidate_id"].isin(required_ids)].itertuples(index=False):
        definition = pd.Series(row._asdict())
        detail = _detail_signal(combined, definition)
        aligned = _align(detail, calendar).reset_index(names="date")
        chart = pd.DataFrame({"date": calendar})
        for column in ("value", "ema", "start_line", "end_line", "rsi", "lower", "upper", "close", "high", "low"):
            chart[column] = detail[column].reindex(calendar).to_numpy() if column in detail else np.nan
        chart = chart.merge(aligned, on="date", how="left")
        expected = core.loc[core["candidate_id"].eq(row.candidate_id), ["date", "risk_state", "risk_start", "risk_end", "valid_signal"]]
        chart = chart.merge(expected, on="date", how="left", suffixes=("", "_expected"))
        for column in ("risk_state", "risk_start", "risk_end", "valid_signal"):
            chart[f"{column}_parity"] = chart[column].eq(chart[f"{column}_expected"])
        chart = chart.drop(columns=[f"{column}_expected" for column in ("risk_state", "risk_start", "risk_end", "valid_signal")])
        chart.insert(0, "component_id", row.candidate_id)
        chart.insert(1, "component_label", f"{row.indicator_name} · {row.param_id}")
        chart.insert(2, "component_kind", "CORE_INDICATOR")
        parts.append(chart)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _component_history(
    live_payload: dict[str, Any], final: pd.DataFrame, definitions: pd.DataFrame, children: pd.DataFrame
) -> pd.DataFrame:
    core = _frame_with_date(live_payload["core"])
    child = _frame_with_date(live_payload["child"])
    bases = {str(row.candidate_id): pd.Timestamp(row.basis_date) if row.basis_date else None for row in live_payload["snapshot"].itertuples(index=False)}
    definition_map = definitions.set_index("candidate_id").to_dict("index")
    parts: list[pd.DataFrame] = []
    for parent in final.itertuples(index=False):
        parent_id = str(parent.candidate_id)
        basis = bases.get(parent_id)
        if basis is None:
            continue
        if parent.model_family == "COMBO1":
            for order, component_id in enumerate(str(parent.candidate_ids).split("|"), start=1):
                meta = definition_map[component_id]
                part = core.loc[core["candidate_id"].eq(component_id), ["date", "risk_state", "risk_start", "risk_end", "valid_signal"]].copy()
                part = part.loc[part["date"].le(basis)].rename(columns={"risk_state": "component_risk_state", "valid_signal": "component_valid"})
                part.insert(0, "parent_candidate_id", parent_id)
                part.insert(1, "component_id", component_id)
                part.insert(2, "component_order", order)
                part.insert(3, "component_kind", "CORE_INDICATOR")
                part.insert(4, "component_label", f"{meta['indicator_name']} · {meta['param_id']}")
                parts.append(part)
        else:
            mappings = children.loc[children["parent_combo2_id"].eq(parent_id)].sort_values("child_order")
            for mapping in mappings.itertuples(index=False):
                part = child.loc[child["combo_id"].eq(mapping.child_combo1_id), ["date", "active_count", "raw_risk_state", "risk_start", "risk_end", "valid"]].copy()
                part = part.loc[part["date"].le(basis)].rename(columns={"raw_risk_state": "component_risk_state", "valid": "component_valid"})
                part.insert(0, "parent_candidate_id", parent_id)
                part.insert(1, "component_id", mapping.child_combo1_id)
                part.insert(2, "component_order", int(mapping.child_order))
                part.insert(3, "component_kind", "CHILD_COMBO1_RAW_STATE")
                part.insert(4, "component_label", f"[조합1] 구성 후보 (지표 {len(str(mapping.child_candidate_ids).split('|'))}개/K{int(mapping.child_K)}/L{int(mapping.child_L)})")
                parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _candidate_history(live_payload: dict[str, Any], final: pd.DataFrame) -> pd.DataFrame:
    t1 = _frame_with_date(live_payload["t1"]).rename(columns={"combo_id": "candidate_id"})
    bases = {str(row.candidate_id): pd.Timestamp(row.basis_date) if row.basis_date else None for row in live_payload["snapshot"].itertuples(index=False)}
    allowed = set(final["candidate_id"].astype(str))
    parts = []
    for candidate_id, group in t1.loc[t1["candidate_id"].isin(allowed)].groupby("candidate_id", sort=False):
        basis = bases.get(str(candidate_id))
        if basis is not None:
            parts.append(group.loc[group["date"].le(basis)].copy())
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=t1.columns)


def _benchmark_history(live_payload: dict[str, Any], final: pd.DataFrame) -> pd.DataFrame:
    combined = _frame_with_date(live_payload["combined"])[["date", "kosdaq_close"]]
    bases = {str(row.candidate_id): pd.Timestamp(row.basis_date) if row.basis_date else None for row in live_payload["snapshot"].itertuples(index=False)}
    parts = []
    for candidate_id in final["candidate_id"].astype(str):
        basis = bases.get(candidate_id)
        if basis is not None:
            part = combined.loc[combined["date"].le(basis)].copy()
            part.insert(0, "candidate_id", candidate_id)
            parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["candidate_id", "date", "kosdaq_close"])


def _cycle_counts(position: pd.Series, short_cycle_days: int = 20) -> tuple[int, int]:
    pos = pd.Series(position).astype(int).reset_index(drop=True)
    in_cycle = False
    start = 0
    completed = 0
    short = 0
    for index in range(1, len(pos)):
        previous, current = int(pos.iloc[index - 1]), int(pos.iloc[index])
        if not in_cycle and previous == 1 and current == 0:
            in_cycle, start = True, index
        elif in_cycle and previous == 0 and current == 1:
            completed += 1
            short += int(index - start <= short_cycle_days)
            in_cycle = False
    return completed, short


def _window_metrics(close: pd.Series, position: pd.Series, start: pd.Timestamp, end: pd.Timestamp, *, cost_bps: float, buyhold: bool) -> dict[str, float | int]:
    index = close.loc[close.index.to_series().between(start, end)].index
    if len(index) == 0:
        return {"asset": np.nan, "mdd": np.nan, "cagr": np.nan, "risk_off_ratio": np.nan, "cycle": 0, "short_cycle": 0}
    returns = close.pct_change().fillna(0.0).reindex(index).fillna(0.0)
    active = pd.Series(1.0, index=index) if buyhold else position.reindex(index).astype(float)
    if active.isna().any():
        return {"asset": np.nan, "mdd": np.nan, "cagr": np.nan, "risk_off_ratio": np.nan, "cycle": 0, "short_cycle": 0}
    trade = pd.Series(0.0, index=index) if buyhold else active.diff().abs().fillna(0.0)
    equity = INITIAL_CAPITAL * (1.0 + returns * active - trade * (cost_bps / 10000.0)).cumprod()
    years = max(float((index[-1] - index[0]).days) / 365.25, 1.0 / 365.25)
    mdd = float((equity / equity.cummax() - 1.0).min())
    cycles, short = _cycle_counts(active)
    return {
        "asset": float(equity.iloc[-1]),
        "mdd": mdd,
        "cagr": float((equity.iloc[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0),
        "risk_off_ratio": 0.0 if buyhold else float((active == 0.0).mean()),
        "cycle": cycles,
        "short_cycle": short,
    }


def _frozen_display_metrics(final: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    frozen = pd.read_parquet(ASSETS / "frozen/frozen_kosdaq_macro_snapshot.parquet")
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    frozen = frozen.loc[frozen["kosdaq_performance_calendar_eligible"].astype(bool)].set_index("date").sort_index()
    close = pd.to_numeric(frozen["kosdaq_close"], errors="coerce")
    t1 = pd.read_parquet(ASSETS / "frozen/final_t1_reference.parquet")
    t1["date"] = pd.to_datetime(t1["date"]).dt.normalize()
    cutoff = pd.Timestamp(FROZEN_CUTOFF)
    start = pd.Timestamp(EVALUATION_START)
    ten_year_start = close.loc[close.index >= cutoff - pd.DateOffset(years=10)].index.min()
    hold_rows = []
    for window, window_start in (("10Y", ten_year_start), ("FULL", start)):
        hold_rows.append({"candidate_id": "KOSDAQ_HOLD", "window": window, **_window_metrics(close, pd.Series(dtype=float), window_start, cutoff, cost_bps=0.0, buyhold=True)})
    rows = []
    for candidate_id in final["candidate_id"].astype(str):
        state = t1.loc[t1["combo_id"].eq(candidate_id)].set_index("date").sort_index()
        for window, window_start in (("10Y", ten_year_start), ("FULL", start)):
            rows.append({"candidate_id": candidate_id, "window": window, **_window_metrics(close, state["invest_position"], window_start, cutoff, cost_bps=10.0, buyhold=False)})
    return pd.DataFrame(rows), pd.DataFrame(hold_rows), {
        "evaluation_start": _date(start),
        "frozen_cutoff": _date(cutoff),
        "ten_year_start": _date(ten_year_start),
    }


def build_presentation_payload(live_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, network-free display payload from Stage 3 output."""
    final, definitions, children = _final_and_definitions()
    required_ids = _required_core_ids(final, children)
    final_ids = final["candidate_id"].astype(str).tolist()
    snapshot = live_payload["snapshot"].copy().set_index("candidate_id").reindex(final_ids).reset_index()
    for column in ("model_family", "display_slot", "display_role", "K", "L"):
        snapshot[column] = final[column].to_numpy()
    candidate_history = _candidate_history(live_payload, final)
    component_history = _component_history(live_payload, final, definitions, children)
    component_chart_history = _core_chart_history(live_payload, definitions, required_ids)
    benchmark_history = _benchmark_history(live_payload, final)
    display_metrics, hold_metrics, windows = _frozen_display_metrics(final)
    return {
        "presentation_contract": "kosdaq_macro7_presentation_payload_v1",
        "frozen_cutoff": _date(FROZEN_CUTOFF),
        "as_of_utc": live_payload["as_of_utc"],
        "market_session_status": live_payload["market_session_status"],
        "provisional_intraday_model_state": live_payload["provisional_intraday_model_state"],
        "snapshot": snapshot,
        "candidate_history": candidate_history,
        "component_history": component_history,
        "component_chart_history": component_chart_history,
        "benchmark_history": benchmark_history,
        "performance_history": live_payload["performance"].copy(),
        "live_metrics": live_payload["metrics"].copy(),
        "frozen_display_metrics": display_metrics,
        "benchmark_display_metrics": hold_metrics,
        "backtest_windows": windows,
        "source_status": live_payload["source_status"].copy(),
        "merge": dict(live_payload["merge"]),
        "final10": final.copy(),
        "ui_side_model_calculation_count": 0,
        "combo2_input_semantics": live_payload["combo2_input_semantics"],
        "final_t1_application_count": live_payload["final_t1_application_count"],
        "invalid_component_as_risk_on_count": live_payload["invalid_component_as_risk_on_count"],
    }
