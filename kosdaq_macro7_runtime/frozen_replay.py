"""Independent, network-free Frozen replay for the locked Macro7 models."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ASSET_ROOT = Path(__file__).resolve().parents[1] / "kosdaq_macro7_assets"
TRADING_DAYS = 252.0
INITIAL_CAPITAL = 100.0


def _state_events(starts: pd.Series, ends: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    state = np.zeros(len(starts), dtype=bool)
    start = np.zeros(len(starts), dtype=bool)
    end = np.zeros(len(starts), dtype=bool)
    active = False
    for index, (begin, finish) in enumerate(zip(starts.to_numpy(bool), ends.to_numpy(bool))):
        if not active and begin:
            active = True
            start[index] = True
        elif active and finish:
            active = False
            end[index] = True
        state[index] = active
    return pd.Series(state, index=starts.index), pd.Series(start, index=starts.index), pd.Series(end, index=starts.index)


def _align(signal: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    aligned = pd.DataFrame(index=calendar)
    if signal.empty:
        aligned["risk_state"] = False
        aligned["risk_start"] = False
        aligned["risk_end"] = False
        aligned["valid_signal"] = False
        return aligned
    source = signal.copy().sort_index()
    union = source.index.union(calendar).sort_values()
    state = source["risk_state"].astype(np.int8).reindex(union).ffill().fillna(0).astype(bool).reindex(calendar).fillna(False).astype(bool)
    previous = state.shift(1, fill_value=False)
    valid_dates = source.index[source["valid_signal"].astype(bool)]
    first_valid = valid_dates.min() if len(valid_dates) else source.index.min()
    aligned["risk_state"] = state
    aligned["risk_start"] = state & ~previous
    aligned["risk_end"] = ~state & previous
    aligned["valid_signal"] = pd.Series(calendar >= first_valid, index=calendar, dtype=bool)
    return aligned


def _dynamic_level(series: pd.Series, params: dict[str, Any], event_allowed: pd.Series | None = None) -> pd.DataFrame:
    value = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if value.empty:
        return pd.DataFrame()
    span, window = int(params["ema_span"]), int(params["window"])
    out = pd.DataFrame({"value": value})
    out["ema"] = out["value"] if span == 1 else out["value"].ewm(span=span, adjust=False, min_periods=max(3, span // 2)).mean()
    out = out.dropna().copy()
    min_periods = max(20, window // 2)
    out["start_line"] = out["ema"].rolling(window, min_periods=min_periods).quantile(float(params["start_q"])).shift(1)
    out["end_line"] = out["ema"].rolling(window, min_periods=min_periods).quantile(float(params["end_q"])).shift(1)
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()
    begin = (out["ema"].shift(1) >= out["start_line"].shift(1)) & (out["ema"] < out["start_line"])
    finish = (out["ema"].shift(1) <= out["end_line"].shift(1)) & (out["ema"] > out["end_line"])
    if event_allowed is not None:
        allowed = event_allowed.reindex(out.index).fillna(False).astype(bool)
        begin &= allowed
        finish &= allowed
    state, start, end = _state_events(begin.fillna(False), finish.fillna(False))
    out["risk_state"], out["risk_start"], out["risk_end"], out["valid_signal"] = state, start, end, True
    return out


def _rsi(close: pd.Series, params: dict[str, Any]) -> pd.DataFrame:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    period, lookback = int(params["period"]), int(params["lookback"])
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rsi = 100 - 100 / (1 + gain / (loss + 1e-10))
    min_periods = max(lookback // 2, 10)
    lower = rsi.rolling(lookback, min_periods=min_periods).quantile(float(params["lower_q"]))
    upper = rsi.rolling(lookback, min_periods=min_periods).quantile(float(params["upper_q"]))
    out = pd.concat([rsi.rename("rsi"), lower.rename("lower"), upper.rename("upper")], axis=1).dropna()
    if out.empty:
        return pd.DataFrame()
    state, start, end = _state_events(out["rsi"] >= out["upper"], out["rsi"] <= out["lower"])
    out["risk_state"], out["risk_start"], out["risk_end"], out["valid_signal"] = state, start, end, True
    return out


def _bollinger(frame: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    out = frame[["kosdaq_close", "kosdaq_high", "kosdaq_low", "kosdaq_ohlc_signal_eligible"]].copy()
    out = out.rename(columns={"kosdaq_close": "close", "kosdaq_high": "high", "kosdaq_low": "low"})
    eligible = out.pop("kosdaq_ohlc_signal_eligible").astype(bool)
    out.loc[~eligible, ["close", "high", "low"]] = np.nan
    out = out.dropna().sort_index()
    window = int(params["window"])
    middle = out["close"].rolling(window, min_periods=window).mean()
    deviation = out["close"].rolling(window, min_periods=window).std()
    out["upper"] = middle + float(params["std_multiplier"]) * deviation
    out["lower"] = middle - float(params["std_multiplier"]) * deviation
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()
    buy_flag = out["low"] <= out["lower"]
    sell_flag = out["high"] >= out["upper"]
    full_eligible = eligible.reindex(out.index).fillna(False)
    allowed = full_eligible & full_eligible.shift(1, fill_value=False)
    begin = sell_flag.shift(1, fill_value=False) & (out["high"] < out["upper"]) & allowed
    finish = buy_flag.shift(1, fill_value=False) & (out["low"] > out["lower"]) & allowed
    state, start, end = _state_events(begin, finish)
    out["risk_state"], out["risk_start"], out["risk_end"], out["valid_signal"] = state, start, end, True
    return out


def _wilder_atr(frame: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = (pd.to_numeric(frame[column], errors="coerce") for column in ["kosdaq_high", "kosdaq_low", "kosdaq_close"])
    eligible = frame["kosdaq_ohlc_signal_eligible"].astype(bool)
    high, low = high.where(eligible), low.where(eligible)
    previous_close = close.shift(1)
    tr = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    valid = tr.dropna()
    if len(valid) < period:
        return result
    first = valid.index[period - 1]
    value = float(valid.iloc[:period].mean())
    result.loc[first] = value
    for day, tr_value in valid.iloc[period:].items():
        value = (value * (period - 1) + float(tr_value)) / period
        result.loc[day] = value
    return result


def _candidate_frame(frozen: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    params = json.loads(row.params_json)
    calendar = frozen.index
    indicator = str(row.indicator_id)
    kind = str(row.kind)
    if kind == "rsi":
        signal = _rsi(frozen["kosdaq_close"], params)
    elif kind == "bollinger":
        signal = _bollinger(frozen, params)
    elif kind == "yield_slope":
        window = int(params["slope_window"])
        values = pd.to_numeric(frozen["us_10y_yield"], errors="coerce")
        x = np.arange(window, dtype=float)
        centered = x - x.mean()
        denominator = float(np.dot(centered, centered))
        slope = values.rolling(window, min_periods=window).apply(lambda series: np.nan if np.isnan(series).any() else float(np.dot(centered, series) / denominator), raw=True)
        signal = _dynamic_level(-slope, {"ema_span": params["ema_span"], "window": params["threshold_window"], "start_q": params["start_q"], "end_q": params["end_q"]})
    else:
        if indicator == "kosdaq_natr":
            value = -(100.0 * _wilder_atr(frozen, int(params["natr_n"])) / pd.to_numeric(frozen["kosdaq_close"], errors="coerce"))
            eligible = frozen["kosdaq_ohlc_signal_eligible"].astype(bool)
            signal = _dynamic_level(value, params, eligible & eligible.shift(1, fill_value=False))
        elif indicator == "kosdaq_hv":
            close = pd.to_numeric(frozen["kosdaq_close"], errors="coerce").where(lambda series: series > 0)
            value = -(np.log(close / close.shift(1)).rolling(int(params["hv_n"]), min_periods=int(params["hv_n"])).std(ddof=1) * np.sqrt(252.0))
            signal = _dynamic_level(value, params)
        else:
            source = str(row.source_column)
            signal = _dynamic_level(frozen[source], params)
    result = _align(signal, calendar)
    result.insert(0, "date", calendar)
    return result


def _hysteresis(active: np.ndarray, k: int, l: int) -> np.ndarray:
    state = np.zeros(len(active), dtype=bool)
    current = False
    for day, count in enumerate(active):
        current = True if count >= k else False if count <= l else current
        state[day] = current
    return state


def _combine(core: pd.DataFrame, combo_id: str, candidate_ids: list[str], k: int, l: int, evaluation_start: str) -> pd.DataFrame:
    selected = core.loc[(core.candidate_id.isin(candidate_ids)) & (core.date.ge(pd.Timestamp(evaluation_start)))]
    state = selected.pivot(index="date", columns="candidate_id", values="risk_state").reindex(columns=candidate_ids).astype(bool)
    valid = selected.pivot(index="date", columns="candidate_id", values="valid_signal").reindex(columns=candidate_ids).astype(bool)
    composite_valid = valid.all(axis=1)
    # The research contract requires every input to be valid in the evaluation window.
    # Keep invalidity separate; it is never normalized into an inactive/Risk-on state.
    invalid_component_days = int((~composite_valid).sum())
    if invalid_component_days:
        raise ValueError(f"INVALID_NOT_RISK_ON: {combo_id} has {invalid_component_days} invalid evaluation dates")
    active = state.sum(axis=1).to_numpy(dtype=np.uint8)
    raw = _hysteresis(active, int(k), int(l))
    previous = np.r_[False, raw[:-1]]
    return pd.DataFrame({"combo_id": combo_id, "date": state.index, "active_count": active, "raw_risk_state": raw, "valid": composite_valid.to_numpy(bool), "risk_start": raw & ~previous, "risk_end": ~raw & previous, "invalid_component_days": invalid_component_days, "invalid_component_as_risk_on": 0})


def _final_t1(raw: pd.DataFrame) -> pd.DataFrame:
    out = raw.copy()
    risk_off = out.raw_risk_state.to_numpy(bool)
    out["risk_off_t1"] = np.r_[False, risk_off[:-1]]
    out["invest_position"] = (~out.risk_off_t1).astype(np.int8)
    return out


def _performance(frozen: pd.DataFrame, states: pd.DataFrame, evaluation_start: str, cost_bps: float) -> pd.DataFrame:
    frozen = frozen.loc[frozen["kosdaq_performance_calendar_eligible"].astype(bool)]
    price = pd.to_numeric(frozen["kosdaq_close"], errors="coerce")
    returns = price.pct_change().fillna(0.0)
    eval_dates = frozen.index[frozen.index >= pd.Timestamp(evaluation_start)]
    result = states.set_index("date").reindex(eval_dates).copy()
    result["benchmark_return"] = returns.reindex(eval_dates).to_numpy(float)
    result["trade"] = result.invest_position.diff().abs().fillna(0.0)
    result["strategy_return"] = result.invest_position * result.benchmark_return - result.trade * (cost_bps / 10000.0)
    result["equity"] = INITIAL_CAPITAL * (1.0 + result.strategy_return).cumprod()
    return result.reset_index(names="date")


def _metrics(performance: pd.DataFrame) -> dict[str, float]:
    equity = performance.equity.to_numpy(float)
    dates = pd.to_datetime(performance.date)
    years = max(float((dates.iloc[-1] - dates.iloc[0]).days) / 365.25, 1.0 / 365.25)
    cagr = float((equity[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)
    mdd = float(np.min(equity / np.maximum.accumulate(equity) - 1.0))
    calmar = float(cagr / abs(mdd)) if mdd < 0 else np.nan
    return {"total_return": float(equity[-1] / INITIAL_CAPITAL - 1.0), "CAGR": cagr, "MDD": mdd, "Calmar": calmar}


def run_frozen_replay(asset_root: Path | None = None) -> dict[str, pd.DataFrame | dict[str, Any]]:
    root = asset_root or ASSET_ROOT
    manifest = json.loads((root / "kosdaq_macro7_final_manifest.json").read_text(encoding="utf-8"))
    evaluation_start = manifest["contracts"]["evaluation"]["evaluation_start"]
    final = pd.read_csv(root / "kosdaq_macro7_final10.csv")
    children = pd.read_csv(root / "kosdaq_macro7_combo2_child_mapping.csv")
    definitions = pd.read_csv(root / "kosdaq_macro7_signal_definitions.csv")
    frozen = pd.read_parquet(root / "frozen/frozen_kosdaq_macro_snapshot.parquet")
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    frozen = frozen.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    core_frames = []
    for row in definitions.itertuples(index=False):
        frame = _candidate_frame(frozen, pd.Series(row._asdict()))
        frame.insert(0, "candidate_id", row.candidate_id)
        core_frames.append(frame)
    core = pd.concat(core_frames, ignore_index=True)
    combo1_records = []
    for row in final.loc[final.model_family.eq("COMBO1")].itertuples(index=False):
        combo1_records.append(_combine(core, row.candidate_id, str(row.candidate_ids).split("|"), int(row.K), int(row.L), evaluation_start))
    final_combo1 = pd.concat(combo1_records, ignore_index=True)
    child_records = []
    for child_id, group in children.groupby("child_combo1_id", sort=True):
        item = group.iloc[0]
        child_records.append(_combine(core, child_id, str(item.child_candidate_ids).split("|"), int(item.child_K), int(item.child_L), evaluation_start))
    child = pd.concat(child_records, ignore_index=True)
    child_core = child.rename(columns={"combo_id": "candidate_id", "raw_risk_state": "risk_state", "valid": "valid_signal"})[["candidate_id", "date", "active_count", "risk_state", "valid_signal", "risk_start", "risk_end"]]
    combo2_records = []
    for row in final.loc[final.model_family.eq("COMBO2")].itertuples(index=False):
        ids = children.loc[children.parent_combo2_id.eq(row.candidate_id)].sort_values("child_order").child_combo1_id.tolist()
        combo2_records.append(_combine(child_core, row.candidate_id, ids, int(row.K), int(row.L), evaluation_start))
    final_combo2 = pd.concat(combo2_records, ignore_index=True)
    all_final = pd.concat([final_combo1, final_combo2], ignore_index=True)
    t1 = pd.concat([_final_t1(group) for _, group in all_final.groupby("combo_id", sort=True)], ignore_index=True)
    performances = []
    metrics: list[dict[str, Any]] = []
    for combo_id, group in t1.groupby("combo_id", sort=True):
        performance = _performance(frozen, group, manifest["contracts"]["evaluation"]["evaluation_start"], manifest["contracts"]["cost"]["transaction_cost_bps"])
        performances.append(performance)
        metrics.append({"candidate_id": combo_id, **_metrics(performance)})
    return {"core": core, "child": child, "final_combo1": final_combo1, "final_combo2": final_combo2, "t1": t1, "performance": pd.concat(performances, ignore_index=True), "metrics": pd.DataFrame(metrics)}
