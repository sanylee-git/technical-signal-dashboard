"""Deterministic S&P Core15/Final10 replay from dashboard-owned Frozen assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


INITIAL_CAPITAL = 100.0
TRANSACTION_COST_BPS = 0.0
EVALUATION_START = pd.Timestamp("2008-04-01")
EVALUATION_END = pd.Timestamp("2026-08-21")


def _state_from_events(start_event: pd.Series, end_event: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    index = start_event.index.union(end_event.index).sort_values()
    starts = start_event.reindex(index, fill_value=False).to_numpy(dtype=bool)
    ends = end_event.reindex(index, fill_value=False).to_numpy(dtype=bool)
    state = np.zeros(len(index), dtype=bool)
    start_out = np.zeros(len(index), dtype=bool)
    end_out = np.zeros(len(index), dtype=bool)
    in_risk = False
    for position in range(len(index)):
        if not in_risk and starts[position]:
            in_risk = True
            start_out[position] = True
        elif in_risk and ends[position]:
            in_risk = False
            end_out[position] = True
        state[position] = in_risk
    return pd.Series(state, index=index), pd.Series(start_out, index=index), pd.Series(end_out, index=index)


def _dynamic_signal(series: pd.Series, params: dict[str, object], event_allowed: pd.Series | None = None) -> pd.DataFrame:
    out = pd.DataFrame({"value": pd.to_numeric(series, errors="coerce")}).dropna().sort_index()
    if out.empty:
        return pd.DataFrame()
    ema_span = int(params["ema_span"])
    out["ema"] = out["value"] if ema_span == 1 else out["value"].ewm(span=ema_span, adjust=False, min_periods=max(3, ema_span // 2)).mean()
    out = out.dropna().copy()
    threshold_window = int(params["threshold_window"] if "threshold_window" in params else params["window"])
    minimum = max(20, threshold_window // 2)
    out["start_line"] = out["ema"].rolling(threshold_window, min_periods=minimum).quantile(float(params["start_q"])).shift(1)
    out["end_line"] = out["ema"].rolling(threshold_window, min_periods=minimum).quantile(float(params["end_q"])).shift(1)
    out = out.dropna().copy()
    if out.empty:
        return out
    previous_ema = out["ema"].shift(1)
    start = (previous_ema >= out["start_line"]) & (out["ema"] < out["start_line"])
    end = (previous_ema <= out["end_line"]) & (out["ema"] > out["end_line"])
    if event_allowed is not None:
        allowed = event_allowed.reindex(out.index).fillna(False).astype(bool)
        start &= allowed
        end &= allowed
    state, starts, ends = _state_from_events(start.fillna(False), end.fillna(False))
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start"] = starts.reindex(out.index).astype(bool)
    out["risk_end"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _rsi_signal(close: pd.Series, params: dict[str, object]) -> pd.DataFrame:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(int(params["period"]), min_periods=int(params["period"])).mean()
    loss = (-delta.clip(upper=0.0)).rolling(int(params["period"]), min_periods=int(params["period"])).mean()
    rsi = 100.0 - (100.0 / (1.0 + gain / (loss + 1e-10)))
    minimum = max(int(params["lookback"]) // 2, 10)
    lower = rsi.rolling(int(params["lookback"]), min_periods=minimum).quantile(float(params["lower_q"]))
    upper = rsi.rolling(int(params["lookback"]), min_periods=minimum).quantile(float(params["upper_q"]))
    out = pd.concat([rsi.rename("rsi"), lower.rename("lower"), upper.rename("upper")], axis=1).dropna()
    if out.empty:
        return out
    state, starts, ends = _state_from_events(out["rsi"] >= out["upper"], out["rsi"] <= out["lower"])
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start"] = starts.reindex(out.index).astype(bool)
    out["risk_end"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _bollinger_signal(close: pd.Series, high: pd.Series, low: pd.Series, params: dict[str, object], event_allowed: pd.Series) -> pd.DataFrame:
    out = pd.concat([close.rename("close"), high.rename("high"), low.rename("low")], axis=1).apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    middle = out["close"].rolling(int(params["window"]), min_periods=int(params["window"])).mean()
    std = out["close"].rolling(int(params["window"]), min_periods=int(params["window"])).std()
    out["upper"] = middle + float(params["std_multiplier"]) * std
    out["lower"] = middle - float(params["std_multiplier"]) * std
    out = out.dropna().copy()
    if out.empty:
        return out
    start = (out["high"] >= out["upper"]).shift(1, fill_value=False) & (out["high"] < out["upper"])
    end = (out["low"] <= out["lower"]).shift(1, fill_value=False) & (out["low"] > out["lower"])
    allowed = event_allowed.reindex(out.index).fillna(False).astype(bool)
    state, starts, ends = _state_from_events(start & allowed, end & allowed)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start"] = starts.reindex(out.index).astype(bool)
    out["risk_end"] = ends.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    x = np.arange(window, dtype=float)
    centered = x - x.mean()
    denominator = float(np.dot(centered, centered))

    def calculate(values: np.ndarray) -> float:
        return np.nan if np.isnan(values).any() else float(np.dot(centered, values) / denominator)

    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=window).apply(calculate, raw=True)


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    result = pd.Series(np.nan, index=true_range.index, dtype=float)
    valid = true_range.dropna()
    if len(valid) < period:
        return result
    previous_atr = float(valid.iloc[:period].mean())
    result.loc[valid.index[period - 1]] = previous_atr
    for date, value in valid.iloc[period:].items():
        previous_atr = (previous_atr * (period - 1) + float(value)) / period
        result.loc[date] = previous_atr
    return result


def _align_to_calendar(signal: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    risk = np.full(len(calendar), -1, dtype=np.int8)
    valid = np.zeros(len(calendar), dtype=bool)
    start = np.zeros(len(calendar), dtype=bool)
    end = np.zeros(len(calendar), dtype=bool)
    if signal.empty:
        return risk, valid, start, end
    source = signal.sort_index()
    valid = calendar >= source.index.min()
    expanded = source["risk_state"].reindex(source.index.union(calendar).sort_values()).ffill().reindex(calendar)
    risk[valid] = expanded.loc[calendar[valid]].to_numpy(dtype=np.int8)
    start = source["risk_start"].reindex(calendar, fill_value=False).to_numpy(dtype=bool)
    end = source["risk_end"].reindex(calendar, fill_value=False).to_numpy(dtype=bool)
    return risk, valid, start, end


def _panel_series(panel: pd.DataFrame, column: str, transform: str = "identity") -> pd.Series:
    result = pd.Series(pd.to_numeric(panel[column], errors="coerce").to_numpy(dtype=float), index=pd.DatetimeIndex(panel["date"]).normalize())
    return -result if transform == "negate" else result


def _core_detail_signal(panel: pd.DataFrame, record: pd.Series) -> pd.DataFrame:
    """Return the existing Core15 signal frame for presentation only."""
    params = json.loads(str(record.params_json))
    calendar = pd.DatetimeIndex(panel["date"]).normalize()
    indicator = str(record.indicator_id)
    if indicator == "us_10y_nominal_yield_slope":
        signal = _dynamic_signal(-_rolling_slope(_panel_series(panel, "dgs10"), int(params["slope_window"])), params)
    elif indicator == "snp_rsi":
        signal = _rsi_signal(_panel_series(panel, "close"), params)
    else:
        close = _panel_series(panel, "close")
        high = _panel_series(panel, "high")
        low = _panel_series(panel, "low")
        ohlc = pd.Series(panel["ohlc_signal_eligible"].astype(bool).to_numpy(), index=calendar)
        event_allowed = ohlc & ohlc.shift(1, fill_value=False)
        if indicator == "snp_bollinger":
            signal = _bollinger_signal(close.where(ohlc), high.where(ohlc), low.where(ohlc), params, event_allowed)
        elif indicator == "snp_natr":
            source = -(100.0 * _wilder_atr(high.where(ohlc), low.where(ohlc), close, int(params["natr_n"])) / close)
            signal = _dynamic_signal(source, params, event_allowed)
        elif indicator == "snp_hv":
            valid_close = close.where(close > 0.0)
            source = -(np.log(valid_close / valid_close.shift(1)).rolling(int(params["hv_n"]), min_periods=int(params["hv_n"])).std(ddof=1) * np.sqrt(252.0))
            signal = _dynamic_signal(source, params)
        else:
            signal = _dynamic_signal(_panel_series(panel, str(record["source_column"]), str(record["transform"])), params)
    return signal


def _core_signal(panel: pd.DataFrame, record: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    calendar = pd.DatetimeIndex(panel["date"]).normalize()
    signal = _core_detail_signal(panel, record)
    return _align_to_calendar(signal, calendar)


def replay_core(panel: pd.DataFrame, registry: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"]).dt.normalize()
    panel = panel.sort_values("date", kind="mergesort").drop_duplicates("date", keep="last").reset_index(drop=True)
    result: dict[str, dict[str, np.ndarray]] = {}
    for record in registry.sort_values("candidate_id", kind="mergesort").itertuples(index=False):
        raw, valid, start, end = _core_signal(panel, pd.Series(record._asdict()))
        result[str(record.candidate_id)] = {"raw": raw, "valid": valid, "start": start, "end": end}
    return result


def replay_core_chart_history(panel: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Expose precomputed Core15 chart fields without UI-side calculation."""
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame.sort_values("date", kind="mergesort").drop_duplicates("date", keep="last").reset_index(drop=True)
    calendar = pd.DatetimeIndex(frame["date"])
    parts: list[pd.DataFrame] = []
    chart_columns = ("value", "ema", "start_line", "end_line", "rsi", "lower", "upper", "close", "high", "low")
    for record in registry.sort_values("candidate_id", kind="mergesort").itertuples(index=False):
        row = pd.Series(record._asdict())
        detail = _core_detail_signal(frame, row)
        raw, valid, start, end = _align_to_calendar(detail, calendar)
        chart = pd.DataFrame({"date": calendar})
        for column in chart_columns:
            chart[column] = detail[column].reindex(calendar).to_numpy() if column in detail else np.nan
        chart["risk_state"] = raw
        chart["risk_start"] = start
        chart["risk_end"] = end
        chart["valid_signal"] = valid
        chart.insert(0, "component_id", str(record.candidate_id))
        chart.insert(1, "component_label", f"{record.indicator_family} · {str(record.candidate_id).split('__')[-1]}")
        chart.insert(2, "component_kind", "CORE_INDICATOR")
        parts.append(chart)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def performance_calendar(
    panel: pd.DataFrame,
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> tuple[pd.DatetimeIndex, np.ndarray, int, int, np.ndarray]:
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
    mask = frame["performance_calendar_eligible"].astype(bool).to_numpy()
    dates = pd.DatetimeIndex(frame.loc[mask, "date"])
    start = np.flatnonzero(dates == EVALUATION_START)
    target_end = pd.Timestamp(EVALUATION_END if evaluation_end is None else evaluation_end).normalize()
    end = np.flatnonzero(dates == target_end)
    if len(start) != 1 or len(end) != 1 or start[0] == 0:
        raise RuntimeError("Frozen SPX evaluation calendar contract unresolved")
    # Streamlit cache can restore this Pandas-backed view as read-only.
    # Normalize the initial return on a private working copy.
    returns = pd.to_numeric(frame.loc[mask, "spx_performance_return"], errors="coerce").to_numpy(dtype=float, copy=True)
    returns[0] = 0.0
    return dates, mask, int(start[0]), int(end[0]), returns


def _hysteresis(active: np.ndarray, k: int, l: int) -> np.ndarray:
    values = np.asarray(active, dtype=np.int16)
    state = np.zeros(len(values), dtype=bool)
    in_risk = False
    for index, count in enumerate(values):
        if count >= k:
            in_risk = True
        elif count <= l:
            in_risk = False
        state[index] = in_risk
    return state


def _tail_valid_start(values: np.ndarray) -> int:
    invalid = np.flatnonzero(~np.asarray(values, dtype=bool))
    return int(invalid[-1] + 1) if len(invalid) else 0


def _metrics(state: np.ndarray, returns: np.ndarray, dates: pd.DatetimeIndex, prior_position: float) -> dict[str, float | int]:
    risk = np.asarray(state, dtype=bool)
    position = (~risk).astype(float)
    trades = np.abs(np.diff(position, prepend=float(prior_position)))
    net = position * returns - trades * (TRANSACTION_COST_BPS / 10000.0)
    gross = position * returns
    gross_equity = INITIAL_CAPITAL * np.cumprod(1.0 + gross)
    net_equity = INITIAL_CAPITAL * np.cumprod(1.0 + net)
    years = max(float((dates[-1] - dates[0]).days) / 365.25, 1.0 / 365.25)
    cagr = float((net_equity[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)
    running_peak = np.maximum.accumulate(net_equity)
    mdd = float(np.min(net_equity / running_peak - 1.0))
    calmar = float(cagr / abs(mdd)) if mdd < 0.0 else np.nan
    starts = risk & ~np.r_[False, risk[:-1]]
    cycle_count = int(starts.sum())
    completed = 0
    short = 0
    current = 0
    for on in risk:
        if on:
            current += 1
        elif current:
            completed += 1
            short += int(current <= 20)
            current = 0
    return {
        "total_return_before_cost": float(gross_equity[-1] / INITIAL_CAPITAL - 1.0),
        "total_return": float(net_equity[-1] / INITIAL_CAPITAL - 1.0),
        "cagr_before_cost": float((gross_equity[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0),
        "cagr": cagr,
        "mdd": mdd,
        "calmar": calmar,
        "risk_off_ratio": float(risk.mean()),
        "transition_count": int(trades.sum()),
        "annual_turnover": float(trades.sum() / years),
        "completed_cycle_count": completed,
        "short_cycle_20d_ratio": float(short / completed) if completed else 0.0,
    }


def _performance_core(core: dict[str, dict[str, np.ndarray]], mask: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    state: dict[str, np.ndarray] = {}
    valid: dict[str, np.ndarray] = {}
    for candidate_id, value in core.items():
        raw = value["raw"][mask]
        raw_valid = value["valid"][mask] & (raw >= 0)
        t1 = np.full(len(raw), -1, dtype=np.int8)
        t1[1:] = raw[:-1]
        t1_valid = np.zeros(len(raw), dtype=bool)
        t1_valid[1:] = raw_valid[:-1]
        state[candidate_id] = t1
        valid[candidate_id] = t1_valid
    return state, valid


def _build_combo1_state(component_ids: list[str], k: int, l: int, states: dict[str, np.ndarray], valids: dict[str, np.ndarray]) -> tuple[np.ndarray, int, np.ndarray]:
    continuous = np.logical_and.reduce([valids[item] & (states[item] >= 0) for item in component_ids])
    start = _tail_valid_start(continuous)
    if start == 0 and not continuous[0]:
        raise RuntimeError("Invalid Combo1 history start")
    active = np.vstack([states[item][start:] for item in component_ids]).sum(axis=0, dtype=np.int16)
    full = np.full(len(continuous), -1, dtype=np.int8)
    active_full = np.full(len(continuous), -1, dtype=np.int16)
    full[start:] = _hysteresis(active, k, l).astype(np.int8)
    active_full[start:] = active
    return full, start, active_full


def _build_combo1_raw(component_ids: list[str], k: int, l: int, raw: dict[str, np.ndarray], valid: dict[str, np.ndarray]) -> tuple[np.ndarray, int, np.ndarray]:
    continuous = np.logical_and.reduce([valid[item] & (raw[item] >= 0) for item in component_ids])
    start = _tail_valid_start(continuous)
    if start == 0 and not continuous[0]:
        raise RuntimeError("Invalid Combo1 raw history start")
    active = np.vstack([raw[item][start:] for item in component_ids]).sum(axis=0, dtype=np.int16)
    full = np.full(len(continuous), -1, dtype=np.int8)
    active_full = np.full(len(continuous), -1, dtype=np.int16)
    full[start:] = _hysteresis(active, k, l).astype(np.int8)
    active_full[start:] = active
    return full, start, active_full


def replay_combo1_raw_history(
    panel: pd.DataFrame,
    children: pd.DataFrame,
    core: dict[str, dict[str, np.ndarray]],
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return the pinned Combo1 raw-state histories used as Combo2 inputs."""
    dates, mask, _eval_start, eval_end, _returns = performance_calendar(panel, evaluation_end=evaluation_end)
    raw = {candidate_id: value["raw"][mask] for candidate_id, value in core.items()}
    valid = {candidate_id: value["valid"][mask] & (value["raw"][mask] >= 0) for candidate_id, value in core.items()}
    seen: set[str] = set()
    parts: list[pd.DataFrame] = []
    for child in children.sort_values(["child_canonical_parent_id", "child_order"], kind="mergesort").itertuples(index=False):
        child_id = str(child.child_canonical_parent_id)
        if child_id in seen:
            continue
        seen.add(child_id)
        component_ids = str(child.child_component_ids_key).split("|")
        state, _start, active = _build_combo1_raw(component_ids, int(child.child_K), int(child.child_L), raw, valid)
        values = state[: eval_end + 1]
        previous = np.r_[-1, values[:-1]]
        parts.append(pd.DataFrame({
            "combo1_id": child_id,
            "date": dates[: eval_end + 1],
            "raw_risk_state": values,
            "active_count": active[: eval_end + 1],
            "risk_start": (values == 1) & (previous == 0),
            "risk_end": (values == 0) & (previous == 1),
            "valid": values >= 0,
        }))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _replay_final10(
    panel: pd.DataFrame,
    final10: pd.DataFrame,
    children: pd.DataFrame,
    core: dict[str, dict[str, np.ndarray]],
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates, mask, eval_start, eval_end, returns = performance_calendar(panel, evaluation_end=evaluation_end)
    raw_performance = {candidate_id: value["raw"][mask] for candidate_id, value in core.items()}
    valid_performance = {candidate_id: value["valid"][mask] & (value["raw"][mask] >= 0) for candidate_id, value in core.items()}
    canonical, canonical_valid = _performance_core(core, mask)
    rows: list[dict[str, object]] = []
    history_parts: list[pd.DataFrame] = []
    combo2_children = children.groupby("parent_candidate_id", sort=False)
    for record in final10.sort_values("display_order", kind="mergesort").itertuples(index=False):
        candidate_id = str(record.candidate_id)
        if record.family == "Combo1":
            component_ids = str(record.component_ids_key).split("|")
            state, history_start, active_full = _build_combo1_state(component_ids, int(record.K), int(record.L), canonical, canonical_valid)
            evaluation_state = state[eval_start : eval_end + 1]
            prior = float(~state[eval_start - 1].astype(bool))
            semantic = "CORE_CANONICAL_T1_DIRECT_NO_SECOND_SHIFT"
        else:
            child = combo2_children.get_group(candidate_id).sort_values("child_order", kind="mergesort")
            child_raw: dict[str, np.ndarray] = {}
            child_starts: dict[str, int] = {}
            # Combo2 children are defined on the complete source-history raw
            # calendar.  Rebuilding only from the official slice changes the
            # hysteresis seed and is therefore not the frozen research model.
            for child_record in child.itertuples(index=False):
                child_id = str(child_record.child_canonical_parent_id)
                ids = str(child_record.child_component_ids_key).split("|")
                child_raw[child_id], child_starts[child_id], _child_active = _build_combo1_raw(
                    ids,
                    int(child_record.child_K),
                    int(child_record.child_L),
                    {item: value["raw"] for item, value in core.items()},
                    {item: value["valid"] & (value["raw"] >= 0) for item, value in core.items()},
                )
            history_start = max(child_starts.values())
            ordered_child_ids = list(child_raw)
            active = np.vstack([child_raw[item][history_start:] for item in ordered_child_ids]).sum(axis=0, dtype=np.int16)
            combo_raw = _hysteresis(active, int(record.K), int(record.L)).astype(np.int8)
            full_state = np.full(len(panel), -1, dtype=np.int8)
            full_active = np.full(len(panel), -1, dtype=np.int16)
            full_state[history_start + 1:] = combo_raw[:-1]
            full_active[history_start:] = active
            state = full_state[mask]
            active_full = full_active[mask]
            starts = np.flatnonzero(state >= 0)
            if not len(starts):
                raise RuntimeError(f"Combo2 source-history state unavailable: {candidate_id}")
            history_start = int(starts[0])
            evaluation_state = state[eval_start : eval_end + 1]
            if (evaluation_state < 0).any() or state[eval_start - 1] < 0:
                raise RuntimeError(f"Combo2 T+1 state unresolved: {candidate_id}")
            prior = float(~state[eval_start - 1].astype(bool))
            semantic = "CHILD_COMBO1_RAW_RISK_STATE_THEN_FINAL_T1_ONCE"
        if (evaluation_state < 0).any() or state[eval_start - 1] < 0:
            raise RuntimeError(f"Final10 state unresolved: {candidate_id}")
        values = _metrics(evaluation_state.astype(bool), returns[eval_start : eval_end + 1], dates[eval_start : eval_end + 1], prior)
        values.update({
            "candidate_id": candidate_id,
            "family": str(record.family),
            "selection_type": str(record.selection_type),
            "state_semantics": semantic,
            "valid_history_start": str(dates[history_start].date()),
            "state_hash": hashlib.sha256(np.packbits(evaluation_state.astype(np.uint8)).tobytes()).hexdigest(),
        })
        rows.append(values)
        state_history = state[eval_start : eval_end + 1].astype(np.int8)
        active_history = active_full[eval_start : eval_end + 1].astype(np.int16)
        previous = np.r_[state[eval_start - 1], state_history[:-1]]
        history_parts.append(pd.DataFrame({
            "candidate_id": candidate_id,
            "date": dates[eval_start : eval_end + 1],
            "strategy_risk_state": state_history,
            "previous_strategy_risk_state": previous,
            "active_count": active_history,
            "risk_start": (state_history == 1) & (previous == 0),
            "risk_end": (state_history == 0) & (previous == 1),
            "valid": state_history >= 0,
        }))
    metrics = pd.DataFrame(rows).sort_values("candidate_id", kind="mergesort").reset_index(drop=True)
    history = pd.concat(history_parts, ignore_index=True).sort_values(["candidate_id", "date"], kind="mergesort").reset_index(drop=True)
    return metrics, history


def replay_final10(
    panel: pd.DataFrame,
    final10: pd.DataFrame,
    children: pd.DataFrame,
    core: dict[str, dict[str, np.ndarray]],
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    return _replay_final10(panel, final10, children, core, evaluation_end=evaluation_end)[0]


def replay_final10_history(
    panel: pd.DataFrame,
    final10: pd.DataFrame,
    children: pd.DataFrame,
    core: dict[str, dict[str, np.ndarray]],
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return Final10 strategy-state history from the exact Frozen replay."""
    return _replay_final10(panel, final10, children, core, evaluation_end=evaluation_end)[1]


def asset_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
