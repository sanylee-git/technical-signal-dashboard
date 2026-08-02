from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Core15Result:
    candidate_id: str
    frame: pd.DataFrame


def _state_from_start_end_events(start_event: pd.Series, end_event: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    index = start_event.index.union(end_event.index).sort_values()
    starts = start_event.reindex(index, fill_value=False).astype(bool)
    ends = end_event.reindex(index, fill_value=False).astype(bool)
    state = pd.Series(False, index=index, dtype=bool)
    start_signal = pd.Series(False, index=index, dtype=bool)
    end_signal = pd.Series(False, index=index, dtype=bool)

    in_risk = False
    for i, idx in enumerate(index):
        if not in_risk and bool(starts.iloc[i]):
            in_risk = True
            start_signal.iloc[i] = True
        elif in_risk and bool(ends.iloc[i]):
            in_risk = False
            end_signal.iloc[i] = True
        state.iloc[i] = in_risk
    return state, start_signal, end_signal


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(int(period), min_periods=int(period)).mean()
    loss = (-delta.clip(upper=0.0)).rolling(int(period), min_periods=int(period)).mean()
    rs = gain / (loss + 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_dynamic_rsi_thresholds(
    rsi_series: pd.Series,
    lookback: int,
    lower_quantile: float,
    upper_quantile: float,
) -> tuple[pd.Series, pd.Series]:
    min_periods = max(int(lookback) // 2, 10)
    dyn_lower = rsi_series.rolling(int(lookback), min_periods=min_periods).quantile(float(lower_quantile))
    dyn_upper = rsi_series.rolling(int(lookback), min_periods=min_periods).quantile(float(upper_quantile))
    return dyn_lower, dyn_upper


def calculate_bollinger_bands(
    close: pd.Series,
    window: int,
    std_multiplier: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(int(window), min_periods=int(window)).mean()
    std = close.rolling(int(window), min_periods=int(window)).std()
    upper = middle + float(std_multiplier) * std
    lower = middle - float(std_multiplier) * std
    return middle, upper, lower


def rolling_linear_regression_slope(series: pd.Series, window: int) -> pd.Series:
    window = int(window)
    values = pd.to_numeric(series, errors="coerce").sort_index()
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.dot(x_centered, x_centered))

    def _slope(y: np.ndarray) -> float:
        if np.isnan(y).any() or denominator == 0.0:
            return np.nan
        return float(np.dot(x_centered, y) / denominator)

    return values.rolling(window, min_periods=window).apply(_slope, raw=True)


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    period = int(period)
    result = pd.Series(np.nan, index=true_range.index, dtype=float)
    valid_tr = true_range.dropna()
    if len(valid_tr) < period:
        return result
    initial_idx = valid_tr.index[period - 1]
    prev_atr = float(valid_tr.iloc[:period].mean())
    result.loc[initial_idx] = prev_atr
    for idx, tr_value in valid_tr.iloc[period:].items():
        prev_atr = (prev_atr * (period - 1) + float(tr_value)) / period
        result.loc[idx] = prev_atr
    return result


def compute_dynamic_quantile_signal_frame(
    series: pd.Series,
    window: int,
    start_quantile: float,
    end_quantile: float,
    ema_span: int,
) -> pd.DataFrame:
    out = pd.DataFrame({"value": pd.to_numeric(series, errors="coerce")}).dropna().sort_index()
    if out.empty:
        return pd.DataFrame()
    ema_span = int(ema_span)
    ema_col = f"ema{ema_span}"
    if ema_span == 1:
        out[ema_col] = out["value"]
    else:
        out[ema_col] = out["value"].ewm(span=ema_span, adjust=False, min_periods=max(3, ema_span // 2)).mean()
    out = out.dropna().copy()
    min_periods = max(20, int(window) // 2)
    out["risk_start_line"] = out[ema_col].rolling(int(window), min_periods=min_periods).quantile(float(start_quantile)).shift(1)
    out["risk_end_line"] = out[ema_col].rolling(int(window), min_periods=min_periods).quantile(float(end_quantile)).shift(1)
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()

    ema_values = out[ema_col]
    prev_ema = ema_values.shift(1)
    prev_start = out["risk_start_line"].shift(1)
    prev_end = out["risk_end_line"].shift(1)
    start_cross = (prev_ema >= prev_start) & (ema_values < out["risk_start_line"])
    end_cross = (prev_ema <= prev_end) & (ema_values > out["risk_end_line"])
    state, start_signal, end_signal = _state_from_start_end_events(start_cross.fillna(False), end_cross.fillna(False))
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def compute_rsi_signal_frame(close: pd.Series, period: int, lookback: int, lower_q: float, upper_q: float) -> pd.DataFrame:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    rsi = calculate_rsi(close, int(period))
    dyn_lower, dyn_upper = calculate_dynamic_rsi_thresholds(rsi, int(lookback), float(lower_q), float(upper_q))
    out = pd.concat([close.rename("close"), rsi.rename("rsi"), dyn_lower.rename("dyn_lower"), dyn_upper.rename("dyn_upper")], axis=1).dropna()
    if out.empty:
        return pd.DataFrame()
    buy_on = out["rsi"] <= out["dyn_lower"]
    sell_on = out["rsi"] >= out["dyn_upper"]
    state, start_signal, end_signal = _state_from_start_end_events(sell_on, buy_on)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def compute_bollinger_signal_frame(close: pd.Series, high: pd.Series, low: pd.Series, window: int, std_multiplier: float) -> pd.DataFrame:
    out = pd.concat(
        [
            pd.to_numeric(close, errors="coerce").rename("close"),
            pd.to_numeric(high, errors="coerce").rename("high"),
            pd.to_numeric(low, errors="coerce").rename("low"),
        ],
        axis=1,
    ).dropna().sort_index()
    middle, upper, lower = calculate_bollinger_bands(out["close"], int(window), float(std_multiplier))
    out["bb_middle"] = middle
    out["bb_upper"] = upper
    out["bb_lower"] = lower
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()
    buy_flag = out["low"] <= out["bb_lower"]
    sell_flag = out["high"] >= out["bb_upper"]
    buy_signal = buy_flag.shift(1, fill_value=False) & (out["low"] > out["bb_lower"])
    sell_signal = sell_flag.shift(1, fill_value=False) & (out["high"] < out["bb_upper"])
    state, start_signal, end_signal = _state_from_start_end_events(sell_signal, buy_signal)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def compute_yield_slope_signal_frame(
    dgs10: pd.Series,
    slope_window: int,
    ema_span: int,
    threshold_window: int,
    start_quantile: float,
    end_quantile: float,
) -> pd.DataFrame:
    slope = rolling_linear_regression_slope(dgs10, int(slope_window))
    safe_direction_slope = -slope.dropna()
    return compute_dynamic_quantile_signal_frame(
        safe_direction_slope,
        window=int(threshold_window),
        start_quantile=float(start_quantile),
        end_quantile=float(end_quantile),
        ema_span=int(ema_span),
    )


def align_signal_to_benchmark(signal_frame: pd.DataFrame, benchmark_index: pd.DatetimeIndex) -> pd.DataFrame:
    benchmark_index = pd.DatetimeIndex(pd.to_datetime(benchmark_index)).normalize().sort_values().unique()
    aligned = pd.DataFrame(index=benchmark_index)
    if signal_frame is None or signal_frame.empty:
        aligned["risk_state"] = False
        aligned["risk_start_signal"] = False
        aligned["risk_end_signal"] = False
        aligned["valid_signal"] = False
        return aligned
    source = signal_frame.copy()
    source.index = pd.DatetimeIndex(pd.to_datetime(source.index)).normalize()
    source = source.sort_index()
    source = source.loc[~source.index.duplicated(keep="last")]
    union_index = source.index.union(benchmark_index).sort_values()
    state = (
        source["risk_state"]
        .astype(np.int8)
        .reindex(union_index)
        .ffill()
        .fillna(0)
        .astype(bool)
        .reindex(benchmark_index)
        .fillna(False)
        .astype(bool)
    )
    previous_state = state.shift(1, fill_value=False)
    if "valid_signal" in source.columns:
        valid_source = source["valid_signal"].astype(bool)
        valid_dates = valid_source.index[valid_source]
        first_valid = valid_dates.min() if len(valid_dates) else source.index.min()
    else:
        first_valid = source.index.min()
    valid = pd.Series(benchmark_index >= first_valid, index=benchmark_index, dtype=bool)
    aligned["risk_state"] = state.astype(bool)
    aligned["risk_start_signal"] = (state & ~previous_state).astype(bool)
    aligned["risk_end_signal"] = (~state & previous_state).astype(bool)
    aligned["valid_signal"] = valid
    return aligned


def _source_series(frame: pd.DataFrame, source_column: str) -> pd.Series:
    series = pd.to_numeric(frame[source_column], errors="coerce")
    series.index = pd.DatetimeIndex(frame["date"]).normalize()
    return series


def _natr_series(frame: pd.DataFrame, period: int) -> pd.Series:
    index = pd.DatetimeIndex(frame["date"]).normalize()
    close = pd.Series(pd.to_numeric(frame["kospi_close"], errors="coerce").to_numpy(), index=index)
    high = pd.Series(pd.to_numeric(frame["kospi_high"], errors="coerce").to_numpy(), index=index)
    low = pd.Series(pd.to_numeric(frame["kospi_low"], errors="coerce").to_numpy(), index=index)
    atr = wilder_atr(high, low, close, int(period))
    return -(100.0 * atr / close)


def _hv_series(frame: pd.DataFrame, period: int) -> pd.Series:
    index = pd.DatetimeIndex(frame["date"]).normalize()
    close = pd.Series(pd.to_numeric(frame["kospi_close"], errors="coerce").to_numpy(), index=index)
    returns = np.log(close / close.shift(1))
    hv = returns.rolling(int(period), min_periods=int(period)).std() * np.sqrt(252.0)
    return -hv


def compute_core15_component(frame: pd.DataFrame, metadata_row: pd.Series) -> Core15Result:
    candidate_id = str(metadata_row["candidate_id"])
    kind = str(metadata_row["kind"])
    raw_params = metadata_row["params_json"]
    if isinstance(raw_params, dict):
        params = dict(raw_params)
    else:
        import json

        params = json.loads(str(raw_params))

    calendar = pd.DatetimeIndex(pd.to_datetime(frame["date"]).dt.normalize())
    indicator_id = str(metadata_row["indicator_id"])
    source_series_id = str(metadata_row["source_series_id"])

    if kind == "level":
        if source_series_id.startswith("kospi_natr_n"):
            series = _natr_series(frame, int(params.get("natr_n") or source_series_id.replace("kospi_natr_n", "")))
        elif source_series_id.startswith("kospi_hv_n"):
            series = _hv_series(frame, int(params.get("hv_n") or source_series_id.replace("kospi_hv_n", "")))
        else:
            series = _source_series(frame, str(metadata_row["source_column"]))
        signal = compute_dynamic_quantile_signal_frame(
            series,
            window=int(params["window"]),
            start_quantile=float(params["start_q"]),
            end_quantile=float(params["end_q"]),
            ema_span=int(params["ema_span"]),
        )
    elif kind == "rsi":
        signal = compute_rsi_signal_frame(
            _source_series(frame, "kospi_close"),
            period=int(params["period"]),
            lookback=int(params["lookback"]),
            lower_q=float(params["lower_q"]),
            upper_q=float(params["upper_q"]),
        )
    elif kind == "bollinger":
        index = pd.DatetimeIndex(frame["date"]).normalize()
        signal = compute_bollinger_signal_frame(
            pd.Series(pd.to_numeric(frame["kospi_close"], errors="coerce").to_numpy(), index=index),
            pd.Series(pd.to_numeric(frame["kospi_high"], errors="coerce").to_numpy(), index=index),
            pd.Series(pd.to_numeric(frame["kospi_low"], errors="coerce").to_numpy(), index=index),
            window=int(params["window"]),
            std_multiplier=float(params["std_multiplier"]),
        )
    elif kind == "yield_slope":
        signal = compute_yield_slope_signal_frame(
            _source_series(frame, "us_10y_yield"),
            slope_window=int(params["slope_window"]),
            ema_span=int(params["ema_span"]),
            threshold_window=int(params["threshold_window"]),
            start_quantile=float(params["start_q"]),
            end_quantile=float(params["end_q"]),
        )
    else:
        raise ValueError(f"Unsupported Core15 kind for {candidate_id}: {kind}")

    aligned = align_signal_to_benchmark(signal, calendar)
    out = pd.DataFrame(
        {
            "date": aligned.index.strftime("%Y-%m-%d"),
            "risk_state": aligned["risk_state"].astype("int8").to_numpy(),
            "risk_start_signal": aligned["risk_start_signal"].astype("int8").to_numpy(),
            "risk_end_signal": aligned["risk_end_signal"].astype("int8").to_numpy(),
            "valid_signal": aligned["valid_signal"].astype("int8").to_numpy(),
        }
    )
    return Core15Result(candidate_id=candidate_id, frame=out)
