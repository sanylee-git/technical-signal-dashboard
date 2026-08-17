"""KOSDAQ-owned XKRX session asset utilities for Macro7 Live runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


KST = ZoneInfo("Asia/Seoul")
ASSET_PATH = Path(__file__).resolve().parents[1] / "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_asset.parquet"


def load_calendar(path: Path | None = None) -> pd.DataFrame:
    asset = pd.read_parquet(path or ASSET_PATH).copy()
    required = {"session_date", "market_open_kst", "market_close_kst"}
    missing = required.difference(asset.columns)
    if missing:
        raise ValueError(f"KOSDAQ_XKRX_CALENDAR_MISSING_COLUMNS:{sorted(missing)}")
    asset["session_date"] = pd.to_datetime(asset["session_date"], errors="coerce").dt.normalize()
    if asset["session_date"].isna().any() or asset["session_date"].duplicated().any():
        raise ValueError("KOSDAQ_XKRX_CALENDAR_INVALID_DATES")
    opens = pd.to_datetime(asset["market_open_kst"], errors="coerce")
    closes = pd.to_datetime(asset["market_close_kst"], errors="coerce")
    if opens.isna().any() or closes.isna().any() or (opens >= closes).any():
        raise ValueError("KOSDAQ_XKRX_CALENDAR_INVALID_SESSION_TIMES")
    return asset.sort_values("session_date").reset_index(drop=True)


def _as_kst(as_of: datetime | pd.Timestamp | None) -> pd.Timestamp:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return value.tz_convert(KST)


def is_session(date: object, calendar: pd.DataFrame | None = None) -> bool:
    asset = calendar if calendar is not None else load_calendar()
    return pd.Timestamp(date).normalize() in set(pd.DatetimeIndex(asset["session_date"]).normalize())


def latest_completed_session(as_of: datetime | pd.Timestamp | None = None, calendar: pd.DataFrame | None = None) -> pd.Timestamp | None:
    asset = calendar if calendar is not None else load_calendar()
    now_kst = _as_kst(as_of)
    closes = pd.to_datetime(asset["market_close_kst"], errors="coerce", utc=True).dt.tz_convert(KST)
    completed = asset.loc[closes.le(now_kst)]
    if completed.empty:
        return None
    return pd.Timestamp(completed["session_date"].iloc[-1]).normalize()


def latest_allowed_live_session(as_of: datetime | pd.Timestamp | None = None, calendar: pd.DataFrame | None = None) -> pd.Timestamp | None:
    """Use the current XKRX session only while it is actually open or closed."""
    asset = calendar if calendar is not None else load_calendar()
    now_kst = _as_kst(as_of)
    today = now_kst.tz_localize(None).normalize()
    if session_status(as_of, asset) in {"INTRADAY", "AFTER_CLOSE"}:
        return today
    return latest_completed_session(as_of, asset)


def sessions_between(start: object, end: object, calendar: pd.DataFrame | None = None) -> pd.DatetimeIndex:
    asset = calendar if calendar is not None else load_calendar()
    left, right = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    dates = pd.DatetimeIndex(asset.loc[asset["session_date"].between(left, right), "session_date"])
    return dates.normalize().sort_values().unique()


def session_status(as_of: datetime | pd.Timestamp | None = None, calendar: pd.DataFrame | None = None) -> str:
    asset = calendar if calendar is not None else load_calendar()
    now_kst = _as_kst(as_of)
    today = now_kst.tz_localize(None).normalize()
    row = asset.loc[asset["session_date"].eq(today)]
    if row.empty:
        return "NON_SESSION_DAY"
    opened = pd.Timestamp(row["market_open_kst"].iloc[0])
    closed = pd.Timestamp(row["market_close_kst"].iloc[0])
    if now_kst < opened:
        return "PRE_OPEN"
    if now_kst < closed:
        return "INTRADAY"
    return "AFTER_CLOSE"
