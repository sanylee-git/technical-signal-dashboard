from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(int(period), min_periods=int(period)).mean()
    loss = (-delta.clip(upper=0.0)).rolling(int(period), min_periods=int(period)).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi.name = f"rsi_{int(period)}"
    return rsi


def calculate_dynamic_rsi_thresholds(
    rsi_series: pd.Series,
    lookback: int = 60,
    lower_quantile: float = 0.10,
    upper_quantile: float = 0.90,
) -> tuple[pd.Series, pd.Series]:
    """사용자가 지정한 동적 RSI 임계값 계산식. 분위수는 기본 10%/90%."""
    min_periods = max(int(lookback) // 2, 10)
    dyn_lower = rsi_series.rolling(int(lookback), min_periods=min_periods).quantile(float(lower_quantile))
    dyn_upper = rsi_series.rolling(int(lookback), min_periods=min_periods).quantile(float(upper_quantile))
    return dyn_lower, dyn_upper


def calculate_bollinger_bands(
    close: pd.Series,
    window: int = 20,
    std_multiplier: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(int(window), min_periods=int(window)).mean()
    std = close.rolling(int(window), min_periods=int(window)).std()
    upper = middle + float(std_multiplier) * std
    lower = middle - float(std_multiplier) * std
    return middle, upper, lower


def _state_from_start_end_events(
    start_event: pd.Series,
    end_event: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
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


def compute_dynamic_quantile_signal_frame(
    series: pd.Series,
    window: int,
    start_quantile: float,
    end_quantile: float,
    ema_span: int,
) -> pd.DataFrame:
    """높을수록 안전인 시계열에서 하향 돌파 시작/상향 돌파 종료를 계산한다."""
    if series is None or series.dropna().empty:
        return pd.DataFrame()
    if not 0.0 < float(end_quantile) < float(start_quantile) < 1.0:
        raise ValueError("동적 분위수는 0 < end_quantile < start_quantile < 1 이어야 합니다.")

    out = pd.DataFrame({"value": pd.to_numeric(series, errors="coerce")}).dropna().sort_index()
    ema_span = int(ema_span)
    ema_col = f"ema{ema_span}"
    if ema_span == 1:
        out[ema_col] = out["value"]
    else:
        out[ema_col] = out["value"].ewm(
            span=ema_span,
            adjust=False,
            min_periods=max(3, ema_span // 2),
        ).mean()
    out = out.dropna().copy()

    min_periods = max(20, int(window) // 2)
    out["risk_start_line"] = (
        out[ema_col].rolling(int(window), min_periods=min_periods).quantile(float(start_quantile)).shift(1)
    )
    out["risk_end_line"] = (
        out[ema_col].rolling(int(window), min_periods=min_periods).quantile(float(end_quantile)).shift(1)
    )
    out = out.dropna().copy()
    if out.empty:
        return pd.DataFrame()

    ema_values = out[ema_col]
    prev_ema = ema_values.shift(1)
    prev_start = out["risk_start_line"].shift(1)
    prev_end = out["risk_end_line"].shift(1)
    start_cross = (prev_ema >= prev_start) & (ema_values < out["risk_start_line"])
    end_cross = (prev_ema <= prev_end) & (ema_values > out["risk_end_line"])

    state, start_signal, end_signal = _state_from_start_end_events(
        start_cross.fillna(False),
        end_cross.fillna(False),
    )
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def compute_rsi_signal_frame(
    close: pd.Series,
    period: int,
    lookback: int,
    lower_quantile: float = 0.10,
    upper_quantile: float = 0.90,
) -> pd.DataFrame:
    """RSI를 독립 지표로 변환한다: 상단 진입=Risk-off 시작, 하단 진입=종료."""
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    rsi = calculate_rsi(close, int(period))
    dyn_lower, dyn_upper = calculate_dynamic_rsi_thresholds(
        rsi,
        int(lookback),
        lower_quantile=float(lower_quantile),
        upper_quantile=float(upper_quantile),
    )
    out = pd.concat(
        [close.rename("close"), rsi.rename("rsi"), dyn_lower.rename("dyn_lower"), dyn_upper.rename("dyn_upper")],
        axis=1,
    ).dropna()
    if out.empty:
        return pd.DataFrame()

    buy_on = out["rsi"] <= out["dyn_lower"]
    sell_on = out["rsi"] >= out["dyn_upper"]
    state, start_signal, end_signal = _state_from_start_end_events(sell_on, buy_on)
    out["buy_on"] = buy_on.astype(bool)
    out["sell_on"] = sell_on.astype(bool)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def compute_bollinger_signal_frame(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    window: int,
    std_multiplier: float,
) -> pd.DataFrame:
    """BB를 독립 지표로 변환한다. 밴드 접촉/이탈 후 다음 날 재진입 신호를 쓴다."""
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
    out["buy_flag"] = buy_flag.astype(bool)
    out["sell_flag"] = sell_flag.astype(bool)
    out["buy_signal"] = buy_signal.astype(bool)
    out["sell_signal"] = sell_signal.astype(bool)
    out["risk_state"] = state.reindex(out.index).astype(bool)
    out["risk_start_signal"] = start_signal.reindex(out.index).astype(bool)
    out["risk_end_signal"] = end_signal.reindex(out.index).astype(bool)
    out["valid_signal"] = True
    return out


def rolling_linear_regression_slope(series: pd.Series, window: int) -> pd.Series:
    """최근 window개 관측치의 거래일당 선형회귀 기울기."""
    window = int(window)
    values = pd.to_numeric(series, errors="coerce").sort_index()
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.dot(x_centered, x_centered))

    def _slope(y: np.ndarray) -> float:
        if np.isnan(y).any() or denominator == 0.0:
            return np.nan
        return float(np.dot(x_centered, y) / denominator)

    result = values.rolling(window, min_periods=window).apply(_slope, raw=True)
    result.name = f"slope_{window}"
    return result


def compute_yield_slope_signal_frame(
    dgs10: pd.Series,
    slope_window: int,
    ema_span: int,
    threshold_window: int,
    start_quantile: float,
    end_quantile: float,
    precomputed_slope: pd.Series | None = None,
) -> pd.DataFrame:
    slope = precomputed_slope if precomputed_slope is not None else rolling_linear_regression_slope(dgs10, slope_window)
    safe_direction_slope = -slope.dropna()
    return compute_dynamic_quantile_signal_frame(
        safe_direction_slope,
        window=int(threshold_window),
        start_quantile=float(start_quantile),
        end_quantile=float(end_quantile),
        ema_span=int(ema_span),
    )


def align_signal_to_benchmark(signal_frame: pd.DataFrame, benchmark_index: pd.DatetimeIndex) -> pd.DataFrame:
    """불규칙한 FRED/Yahoo 신호를 시장 거래일에 맞춘다. 상태는 유지, 이벤트는 해당일만 True."""
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


def build_hysteresis_combo_state(
    active_count: np.ndarray,
    start_k: int,
    end_l: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not 0 <= int(end_l) < int(start_k):
        raise ValueError("조합 상태 조건은 0 <= end_l < start_k 이어야 합니다.")
    counts = np.asarray(active_count, dtype=np.int16)
    state = np.zeros(counts.size, dtype=bool)
    starts = np.zeros(counts.size, dtype=bool)
    ends = np.zeros(counts.size, dtype=bool)
    in_risk = False
    for i, count in enumerate(counts):
        if not in_risk and int(count) >= int(start_k):
            in_risk = True
            starts[i] = True
        elif in_risk and int(count) <= int(end_l):
            in_risk = False
            ends[i] = True
        state[i] = in_risk
    return state, starts, ends
