"""Frozen-prefix-preserving live runtime for the independent NASDAQ Core15."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import replay_core, replay_final20, replay_final20_history
from .frozen_runtime import run_frozen_runtime
from .live_sources import SOURCE_SPECS, fetch_all_sources


FROZEN_CUTOFF = pd.Timestamp("2026-08-21")
DAILY_FRED_IDS = ("vixcls", "vxvcls", "dfii10", "dgs10", "dgs2", "dgs3mo", "dbaa", "daaa")


def _utc(as_of: datetime | pd.Timestamp | None) -> pd.Timestamp:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def _date(value: object) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "valid" not in frame:
        return pd.DataFrame()
    out = frame.loc[frame["valid"].astype(bool)].copy()
    out["observation_date"] = pd.to_datetime(out["observation_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    return out.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date", keep="last")


def _effective_available(frame: pd.DataFrame, market_dates: pd.DatetimeIndex, lag: int) -> pd.DataFrame:
    source = _valid(frame)
    if source.empty or not len(market_dates):
        return pd.DataFrame(columns=["effective_date", "observation_date", "value"])
    positions = market_dates.searchsorted(pd.DatetimeIndex(source["observation_date"]), side="right") + max(0, int(lag) - 1)
    mask = positions < len(market_dates)
    out = source.loc[mask, ["observation_date", "value"]].copy()
    out["effective_date"] = market_dates.take(positions[mask])
    return out.sort_values(["effective_date", "observation_date"]).drop_duplicates("effective_date", keep="last")


def _available_on_dates(frame: pd.DataFrame, market_dates: pd.DatetimeIndex, lag: int) -> pd.DataFrame:
    effective = _effective_available(frame, market_dates, lag)
    target = pd.DataFrame({"date": market_dates})
    if effective.empty:
        target["value"] = np.nan
        target["observation_date"] = pd.NaT
        return target
    return pd.merge_asof(
        target.sort_values("date"),
        effective[["effective_date", "observation_date", "value"]].sort_values("effective_date"),
        left_on="date",
        right_on="effective_date",
        direction="backward",
    ).drop(columns=["effective_date"])


def _source_is_fresh(frame: pd.DataFrame, spec_id: str, market_calendar: pd.DatetimeIndex) -> bool:
    valid = _valid(frame)
    if valid.empty:
        return False
    latest_observation = pd.Timestamp(valid["observation_date"].max())
    latest_market_date = pd.Timestamp(market_calendar.max())
    if spec_id == "nfci":
        return latest_observation >= latest_market_date - pd.Timedelta(days=12)
    previous_sessions = market_calendar[market_calendar < latest_market_date]
    return len(previous_sessions) > 0 and latest_observation >= pd.Timestamp(previous_sessions.max())


def _latest_available_session(frame: pd.DataFrame, market_dates: pd.DatetimeIndex, lag: int) -> pd.Timestamp | None:
    effective = _effective_available(frame, market_dates, lag)
    if effective.empty:
        return None
    return pd.Timestamp(effective["effective_date"].max()).normalize()


def _rolling_zscore(series: pd.Series, window: int = 252) -> pd.Series:
    mean = series.rolling(window, min_periods=max(30, window // 4)).mean()
    std = series.rolling(window, min_periods=max(30, window // 4)).std().replace(0.0, np.nan)
    return ((series - mean) / std).clip(-3.0, 3.0)


def _build_tail(frozen: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.Timestamp | None]:
    ndx = _valid(frames.get("ndx_ohlcv", pd.DataFrame()))
    ndxe = _valid(frames.get("ndxe_close", pd.DataFrame()))
    if ndx.empty or "observation_date" not in ndx.columns:
        return pd.DataFrame(), [], None
    market = ndx.loc[ndx["observation_date"].gt(FROZEN_CUTOFF)].copy()
    market_dates = pd.DatetimeIndex(market["observation_date"]).normalize().sort_values().unique()
    if not len(market_dates):
        return pd.DataFrame(), [], None
    availability_dates = pd.DatetimeIndex(pd.to_datetime(frozen.loc[frozen["performance_calendar_eligible"].astype(bool), "date"])).normalize().append(market_dates).sort_values().unique()
    source_status: list[dict[str, Any]] = []
    fresh: dict[str, bool] = {}
    strict_limits: list[pd.Timestamp] = []
    for source_id, spec in SOURCE_SPECS.items():
        valid = _valid(frames.get(source_id, pd.DataFrame()))
        latest = valid["observation_date"].max() if not valid.empty else pd.NaT
        okay = source_id in ("ndx_ohlcv", "ndxe_close") or _source_is_fresh(valid, source_id, availability_dates)
        fresh[source_id] = bool(okay)
        available = _latest_available_session(frames.get(source_id, pd.DataFrame()), availability_dates, spec.lag_market_sessions)
        if source_id != "nfci" and available is not None:
            strict_limits.append(available)
        source_status.append({
            "source_id": source_id,
            "provider": spec.provider,
            "provider_identifier": spec.provider_identifier,
            "latest_observation_date": _date(latest),
            "latest_available_session": _date(available),
            "freshness_status": "FRESH" if okay else "STALE_OR_UNAVAILABLE",
        })

    tail = pd.DataFrame({"date": market_dates})
    indexed_ndx = market.set_index("observation_date")
    for raw, target in (("open", "ndx_open"), ("high", "ndx_high"), ("low", "ndx_low"), ("close", "ndx_close")):
        tail[target] = pd.to_numeric(indexed_ndx[raw].reindex(market_dates), errors="coerce").to_numpy()
    indexed_ndxe = ndxe.set_index("observation_date")
    tail["ndxe_close"] = pd.to_numeric(indexed_ndxe["value"].reindex(market_dates), errors="coerce").to_numpy()

    for source_id in DAILY_FRED_IDS + ("nfci",):
        spec = SOURCE_SPECS[source_id]
        available = _available_on_dates(frames[source_id], availability_dates, spec.lag_market_sessions)
        available = available.loc[available["date"].isin(market_dates)].reset_index(drop=True)
        native_frame = _valid(frames.get(source_id, pd.DataFrame()))
        native = pd.Series(dtype=float) if native_frame.empty else native_frame.set_index("observation_date")["value"]
        tail[f"{source_id}_native"] = pd.to_numeric(native.reindex(market_dates), errors="coerce").to_numpy()
        tail[f"{source_id}_available"] = pd.to_numeric(available["value"], errors="coerce").to_numpy()
        tail[f"{source_id}_source_observation_date"] = pd.to_datetime(available["observation_date"], errors="coerce").dt.normalize().to_numpy()

    tail["performance_calendar_eligible"] = tail["ndx_close"].notna() & tail["ndx_close"].gt(0)
    tail["ohlc_signal_eligible"] = tail[["ndx_open", "ndx_high", "ndx_low", "ndx_close"]].notna().all(axis=1)
    tail["breadth_input_eligible"] = tail["ndx_close"].gt(0) & tail["ndxe_close"].gt(0)
    confirmed_basis = min(strict_limits) if strict_limits else None
    return tail, source_status, confirmed_basis


def _merge_frozen_and_tail(frozen: pd.DataFrame, tail: pd.DataFrame) -> pd.DataFrame:
    if tail.empty:
        return frozen.copy()
    out = pd.concat([frozen, tail], ignore_index=True, sort=False).sort_values("date", kind="mergesort").drop_duplicates("date", keep="first").reset_index(drop=True)
    tail_mask = out["date"].gt(FROZEN_CUTOFF)
    out["ndx_performance_return"] = pd.to_numeric(out["ndx_close"], errors="coerce").pct_change()
    out.loc[~tail_mask, "ndx_performance_return"] = frozen["ndx_performance_return"].to_numpy()
    out["ndx_equal_weight_breadth"] = np.log(pd.to_numeric(out["ndxe_close"], errors="coerce") / pd.to_numeric(out["ndx_close"], errors="coerce"))
    # A proxy is complete only when both legs were observed on the same date.
    # Once complete, the existing availability contract carries that completed
    # proxy forward; it never mixes a stale corporate yield with a newer rate.
    frozen_hy_proxy = out["hy_proxy"].copy()
    frozen_ig_proxy = out["ig_proxy"].copy()

    def completed_proxy(left: str, right: str, frozen_values: pd.Series) -> pd.Series:
        left_date = pd.to_datetime(out.get(f"{left}_source_observation_date"), errors="coerce").dt.normalize()
        right_date = pd.to_datetime(out.get(f"{right}_source_observation_date"), errors="coerce").dt.normalize()
        complete = (
            out[left + "_available"].notna()
            & out[right + "_available"].notna()
            & left_date.notna()
            & right_date.notna()
            & left_date.eq(right_date)
        )
        proxy = (out[left + "_available"] - out[right + "_available"]).where(complete)
        proxy.loc[~tail_mask] = frozen_values.loc[~tail_mask]
        return proxy.ffill()

    out["hy_proxy"] = completed_proxy("dbaa", "dgs10", frozen_hy_proxy)
    out["ig_proxy"] = completed_proxy("daaa", "dgs10", frozen_ig_proxy)
    out["vix_spread"] = out["vixcls_available"] - out["vxvcls_available"]
    out["us_10y_2y_spread"] = out["dgs10_available"] - out["dgs2_available"]
    out["us_10y_3m_spread"] = out["dgs10_available"] - out["dgs3mo_available"]
    out["credit_stress_raw"] = pd.concat([
        _rolling_zscore(out["hy_proxy"]), _rolling_zscore(out["nfci_available"]), _rolling_zscore(out["vixcls_available"]),
    ], axis=1).mean(axis=1)
    available = {
        "hy_available": out["hy_proxy"].notna(),
        "ig_available": out["ig_proxy"].notna(),
        "credit_stress_available": out[["hy_proxy", "nfci_available", "vixcls_available"]].notna().all(axis=1),
        "vix_available": out["vixcls_available"].notna(),
        "vix_spread_available": out[["vixcls_available", "vxvcls_available"]].notna().all(axis=1),
        "real_yield_10y_available": out["dfii10_available"].notna(),
        "yield_spread_10y_2y_available": out[["dgs10_available", "dgs2_available"]].notna().all(axis=1),
        "yield_spread_10y_3m_available": out[["dgs10_available", "dgs3mo_available"]].notna().all(axis=1),
        "yield_slope_10y_input_available": out["dgs10_available"].notna(),
    }
    for column, values in available.items():
        out.loc[tail_mask, column] = values.loc[tail_mask].to_numpy()
    out.loc[tail_mask, "core15_input_eligible"] = (
        out.loc[tail_mask, "ohlc_signal_eligible"].astype(bool)
        & out.loc[tail_mask, "breadth_input_eligible"].astype(bool)
        & pd.DataFrame(available).loc[tail_mask].all(axis=1)
    )
    # Frozen rows are immutable research evidence; only post-cutoff rows are derived here.
    for column in frozen.columns:
        if column != "date" and column in out:
            out.loc[: len(frozen) - 1, column] = frozen[column].to_numpy()
    return out


def _continuous_tail(panel: pd.DataFrame) -> pd.Timestamp | None:
    tail = panel.loc[panel["date"].gt(FROZEN_CUTOFF)].sort_values("date")
    if tail.empty:
        return None
    valid = tail["core15_input_eligible"].eq(True)
    invalid = np.flatnonzero(~valid.to_numpy())
    if len(invalid):
        tail = tail.iloc[: int(invalid[0])]
    return None if tail.empty else pd.Timestamp(tail["date"].iloc[-1]).normalize()


def _snapshot(final20: pd.DataFrame, history: pd.DataFrame, panel: pd.DataFrame, basis: pd.Timestamp, *, availability_status: str) -> pd.DataFrame:
    close = panel[["date", "ndx_close"]].copy()
    rows: list[dict[str, Any]] = []
    for candidate in final20.sort_values("display_order", kind="mergesort").itertuples(index=False):
        states = history.loc[history["candidate_id"].eq(candidate.candidate_id) & history["date"].le(basis)].sort_values("date").reset_index(drop=True)
        if states.empty or not states["valid"].all():
            rows.append({"candidate_id": str(candidate.candidate_id), "family": str(candidate.family), "selection_type": str(candidate.selection_type), "basis_date": None, "calculable": False, "availability_status": "UNAVAILABLE"})
            continue
        current = states.iloc[-1]
        prior = states.loc[states["strategy_risk_state"].ne(current.strategy_risk_state)]
        start_index = int(prior.index[-1] + 1) if not prior.empty else 0
        start = pd.Timestamp(states.iloc[start_index]["date"])
        segment = close.loc[close["date"].between(start, basis), "ndx_close"].dropna()
        week_ago = states.iloc[-6] if len(states) >= 6 else None
        rows.append({
            "candidate_id": str(candidate.candidate_id), "family": str(candidate.family), "selection_type": str(candidate.selection_type),
            "basis_date": _date(basis), "calculable": True, "availability_status": availability_status,
            "strategy_risk_state": int(current.strategy_risk_state), "active_count": int(current.active_count), "K": int(candidate.K), "L": int(candidate.L),
            "current_state_start_date": _date(start), "current_duration_trading_days": int(len(states) - start_index),
            "current_segment_return": None if len(segment) < 2 else float(segment.iloc[-1] / segment.iloc[0] - 1.0),
            "current_segment_return_end_date": _date(basis),
            "week_ago_basis_date": None if week_ago is None else _date(week_ago.date),
            "week_ago_strategy_risk_state": None if week_ago is None else int(week_ago.strategy_risk_state),
            "week_ago_active_count": None if week_ago is None else int(week_ago.active_count),
            "today_transition": "RISK_OFF_START" if bool(current.risk_start) else "RISK_OFF_END" if bool(current.risk_end) else "NONE",
        })
    return pd.DataFrame(rows)


def run_live_runtime(*, as_of: datetime | pd.Timestamp | None = None, provider_frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    """Update current states from approved Core15 sources without mutating Frozen history."""
    as_of_utc = _utc(as_of)
    frozen_runtime = run_frozen_runtime()
    frozen = frozen_runtime["panel"].copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    frames = provider_frames if provider_frames is not None else fetch_all_sources(as_of=as_of_utc)
    tail, source_status, confirmed_limit = _build_tail(frozen, frames)
    panel = _merge_frozen_and_tail(frozen, tail)
    continuous_basis = _continuous_tail(panel)
    provisional_basis = FROZEN_CUTOFF if continuous_basis is None else continuous_basis
    provisional_status = (
        "PROVISIONAL_UNAVAILABLE"
        if continuous_basis is None
        else "PROVISIONAL" if provisional_basis > FROZEN_CUTOFF else "CONFIRMED"
    )
    panel = panel.loc[panel["date"].le(provisional_basis)].copy()
    core = replay_core(panel, frozen_runtime["registry"])
    current_metrics = replay_final20(panel, frozen_runtime["final20"], frozen_runtime["children"], core, evaluation_end=provisional_basis)
    history = replay_final20_history(panel, frozen_runtime["final20"], frozen_runtime["children"], core, evaluation_end=provisional_basis)
    confirmed_basis = FROZEN_CUTOFF if confirmed_limit is None else min(pd.Timestamp(confirmed_limit).normalize(), provisional_basis)
    snapshot = _snapshot(
        frozen_runtime["final20"], history, panel, provisional_basis,
        availability_status=provisional_status,
    )
    confirmed_snapshot = _snapshot(
        frozen_runtime["final20"], history, panel, confirmed_basis,
        availability_status="CONFIRMED",
    )
    return {
        "runtime_mode": "LIVE_TAIL",
        "network_access": provider_frames is None,
        "as_of_utc": as_of_utc.isoformat(),
        "basis_date": _date(provisional_basis),
        "confirmed_basis_date": _date(confirmed_basis),
        "provisional_basis_date": _date(provisional_basis),
        "provisional_status": provisional_status,
        "provisional_unavailable_reason": (
            None
            if provisional_status != "PROVISIONAL_UNAVAILABLE"
            else "최신 라이브 원천을 준비하지 못했습니다"
        ),
        "frozen_cutoff": _date(FROZEN_CUTOFF),
        "proxy_only": True,
        "direct_oas_used": False,
        "snapshot": snapshot,
        "confirmed_snapshot": confirmed_snapshot,
        "metrics": frozen_runtime["metrics"],
        "current_metrics": current_metrics,
        "history": history,
        "panel": panel,
        "frozen_panel": frozen_runtime["panel"],
        "frozen_history": frozen_runtime["history"],
        "registry": frozen_runtime["registry"],
        "final20": frozen_runtime["final20"],
        "children": frozen_runtime["children"],
        "core": core,
        "source_status": source_status,
        "live_tail_row_count": int(len(panel.loc[panel["date"].gt(FROZEN_CUTOFF)])),
        "frozen_rows_overwritten": 0,
        "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE",
        "final_t1_application_count": 1,
    }
