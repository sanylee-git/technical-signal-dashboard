"""Deterministic S&P Proxy-only Final10 replay from dashboard-owned assets."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


INITIAL_CAPITAL = 100.0
EVALUATION_START = pd.Timestamp("2008-04-01")
EVALUATION_END = pd.Timestamp("2026-08-21")


def hysteresis(active_count: np.ndarray, k: int, l: int, initial_state: int) -> np.ndarray:
    """Apply the pinned K/L rule with the prior-day raw state as the seed."""
    values = np.asarray(active_count, dtype=np.int16)
    out = np.empty(len(values), dtype=np.int8)
    state = int(initial_state)
    for position, count in enumerate(values):
        if count >= k:
            state = 1
        elif count <= l:
            state = 0
        out[position] = state
    return out


def _rebuild_t1_from_prior_raw(active_count: np.ndarray, k: int, l: int, initial_t1_state: int) -> np.ndarray:
    """Build an official T+1 history whose first row is a pinned prior state."""
    values = np.asarray(active_count, dtype=np.int16)
    if not len(values):
        return np.empty(0, dtype=np.int8)
    out = np.empty(len(values), dtype=np.int8)
    out[0] = int(initial_t1_state)
    state = int(initial_t1_state)
    for position in range(1, len(values)):
        count = values[position]
        if count >= k:
            state = 1
        elif count <= l:
            state = 0
        out[position] = state
    return out


def _continuous_valid(valid: np.ndarray) -> np.ndarray:
    valid = np.asarray(valid, dtype=bool)
    if not valid.all():
        raise RuntimeError("Frozen official replay contains invalid component state")
    return valid


def rebuild_combo1_t1(
    core_t1: pd.DataFrame,
    core_valid: pd.DataFrame,
    component_ids: list[str],
    k: int,
    l: int,
    initial_t1_state: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Rebuild Combo1 official T+1 from Core raw state at D-1.

    Each Core ``t1`` value on date D is its raw state on D-1. Therefore the
    same-date K/L recurrence yields the Combo1 official T+1 state at D.
    """
    missing = [item for item in component_ids if item not in core_t1 or item not in core_valid]
    if missing:
        raise KeyError(f"Core state asset missing candidates: {missing}")
    valid = np.logical_and.reduce([core_valid[item].to_numpy(dtype=bool) for item in component_ids])
    _continuous_valid(valid)
    active = np.vstack([core_t1[item].to_numpy(dtype=np.int8) for item in component_ids]).sum(axis=0, dtype=np.int16)
    return _rebuild_t1_from_prior_raw(active, k, l, initial_t1_state), active


def rebuild_combo1_raw(
    core_raw: pd.DataFrame,
    core_valid: pd.DataFrame,
    component_ids: list[str],
    k: int,
    l: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Rebuild source-history Combo1 raw state from pinned Core raw states."""
    missing = [item for item in component_ids if item not in core_raw or item not in core_valid]
    if missing:
        raise KeyError(f"Core state asset missing candidates: {missing}")
    valid = np.logical_and.reduce([core_valid[item].to_numpy(dtype=bool) for item in component_ids])
    _continuous_valid(valid)
    active = np.vstack([core_raw[item].to_numpy(dtype=np.int8) for item in component_ids]).sum(axis=0, dtype=np.int16)
    return hysteresis(active, k, l, 0), active


def t1_from_raw(raw_state: np.ndarray, source_dates: pd.Series, target_dates: pd.Series) -> np.ndarray:
    """Apply the sole official T+1 shift on a source-history raw state."""
    raw = np.asarray(raw_state, dtype=np.int8)
    source = pd.DatetimeIndex(pd.to_datetime(source_dates)).normalize()
    target = pd.DatetimeIndex(pd.to_datetime(target_dates)).normalize()
    shifted = np.empty(len(raw), dtype=np.int8)
    shifted[0] = 0
    shifted[1:] = raw[:-1]
    lookup = pd.Series(shifted, index=source)
    result = lookup.reindex(target)
    if result.isna().any():
        raise RuntimeError("T+1 target dates missing from source-history calendar")
    return result.to_numpy(dtype=np.int8)


def rebuild_combo2_t1(
    child_combo1_raw: pd.DataFrame,
    child_ids: list[str],
    k: int,
    l: int,
    evaluation_dates: pd.DatetimeIndex,
) -> tuple[np.ndarray, np.ndarray]:
    """Rebuild final Combo2 T+1 from the full source-history child raw states."""
    missing = [item for item in child_ids if item not in child_combo1_raw]
    if missing:
        raise KeyError(f"Combo2 child state asset missing candidates: {missing}")
    values = np.vstack([child_combo1_raw[item].to_numpy(dtype=np.int8) for item in child_ids])
    if (values < 0).any():
        raise RuntimeError("Invalid child Combo1 state cannot be treated as Risk-on")
    active = values.sum(axis=0, dtype=np.int16)
    raw = hysteresis(active, k, l, 0)
    dates = pd.to_datetime(child_combo1_raw["date"]).dt.normalize()
    positions = np.flatnonzero(dates.isin(evaluation_dates).to_numpy())
    if len(positions) != len(evaluation_dates) or positions[0] == 0:
        raise RuntimeError("Combo2 official calendar cannot be aligned to source history")
    return raw[positions - 1], raw


def strategy_metrics(t1_state: np.ndarray, state_dates: pd.Series, benchmark: pd.DataFrame) -> dict[str, float | int | str]:
    state = np.asarray(t1_state, dtype=np.int8)
    frame = benchmark.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    state_index = pd.DatetimeIndex(pd.to_datetime(state_dates)).normalize()
    frame = frame.loc[frame["performance_calendar_eligible"].astype(bool) & frame["date"].isin(state_index)].copy()
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
    if len(frame) != len(state) or (state < 0).any():
        raise RuntimeError("Strategy metric calendar/state mismatch")
    close = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    prior_close = pd.to_numeric(benchmark.assign(date=pd.to_datetime(benchmark["date"]).dt.normalize()).sort_values("date", kind="mergesort").loc[lambda x: x["date"] < frame["date"].iloc[0], "close"], errors="coerce").dropna().iloc[-1]
    returns = np.empty(len(close), dtype=float)
    returns[0] = close[0] / float(prior_close) - 1.0
    returns[1:] = close[1:] / close[:-1] - 1.0
    position = (state == 0).astype(float)
    equity = INITIAL_CAPITAL * np.cumprod(1.0 + position * returns)
    years = (frame["date"].iloc[-1] - frame["date"].iloc[0]).days / 365.25
    cagr = float((equity[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)
    mdd = float(np.min(equity / np.maximum.accumulate(equity) - 1.0))
    previous = np.r_[state[0], state[:-1]]
    starts = (state == 1) & (previous == 0)
    completed = 0
    short = 0
    current = 0
    for value in state:
        if value == 1:
            current += 1
        elif current:
            completed += 1
            short += int(current <= 20)
            current = 0
    return {
        "total_return": float(equity[-1] / INITIAL_CAPITAL - 1.0),
        "cagr": cagr,
        "mdd": mdd,
        "calmar": float(cagr / abs(mdd)) if mdd < 0 else np.nan,
        "risk_off_ratio": float((state == 1).mean()),
        "transition_count": int(np.abs(np.diff((state == 0).astype(np.int8))).sum()),
        "risk_off_cycle_count": int(starts.sum()),
        "short_cycle_20d_ratio": float(short / completed) if completed else 0.0,
        "official_t1_hash": hashlib.sha256(np.packbits(state.astype(np.uint8), bitorder="little").tobytes()).hexdigest(),
    }


def raw_state_metrics(raw_state: np.ndarray, raw_dates: pd.Series, evaluation_dates: pd.Series) -> dict[str, float | int]:
    """Return the research-defined raw-state cycle statistics on a target period."""
    source = pd.Series(np.asarray(raw_state, dtype=np.int8), index=pd.DatetimeIndex(pd.to_datetime(raw_dates)).normalize())
    target = source.reindex(pd.DatetimeIndex(pd.to_datetime(evaluation_dates)).normalize())
    if target.isna().any() or (target.to_numpy(dtype=np.int8) < 0).any():
        raise RuntimeError("Raw-state metric dates unresolved")
    state = target.to_numpy(dtype=np.int8).astype(bool)
    starts = state & ~np.r_[False, state[:-1]]
    cycles = int(starts.sum())
    completed = 0
    short = 0
    current = 0
    for value in state:
        if value:
            current += 1
        elif current:
            completed += 1
            short += int(current <= 20)
            current = 0
    if current:
        completed += 1
        short += int(current <= 20)
    return {
        "risk_off_ratio": float(state.mean()),
        "risk_off_cycle_count": cycles,
        "short_cycle_20d_ratio": float(short / cycles) if cycles else 0.0,
    }


def asset_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
