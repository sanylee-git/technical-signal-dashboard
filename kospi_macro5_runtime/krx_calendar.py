from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd

from .calendar_asset import (
    DEFAULT_CALENDAR_ASSET,
    DEFAULT_CALENDAR_CONTRACT,
    is_session,
    latest_completed_session,
    load_krx_calendar_asset,
    next_session,
    session_close,
)


KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")
CALENDAR_SOURCE = "portable_xkrx_asset_exchange_calendars_build_time"
CALENDAR_VERSION = "d1c2a2r_xkrx_calendar_v1_20260802"


@dataclass(frozen=True)
class KrxCalendarContract:
    calendar_source: str = CALENDAR_SOURCE
    calendar_version: str = CALENDAR_VERSION
    timezone: str = "Asia/Seoul"
    session_asset_path: str = str(DEFAULT_CALENDAR_ASSET)
    contract_path: str = str(DEFAULT_CALENDAR_CONTRACT)
    runtime_requires_exchange_calendars: bool = False
    runtime_fallback_allowed: bool = False
    expected_latest_derived_from_actual_source: bool = False


def is_krx_session(date: object) -> bool:
    return is_session(date)


def kospi_session_is_completed(session_date: object, as_of_utc: object) -> bool:
    if not is_session(session_date):
        return False
    ts = pd.Timestamp(as_of_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(KST) >= session_close(session_date)


def kospi_completed_sessions(start_date: object, end_date: object, as_of_utc: object) -> pd.DataFrame:
    asset = load_krx_calendar_asset()
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    data = asset.loc[pd.to_datetime(asset["session_date"]).dt.normalize().between(start, end)].copy()
    as_of = pd.Timestamp(as_of_utc)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize("UTC")
    as_of_kst = as_of.tz_convert(KST)
    data["is_completed"] = pd.to_datetime(data["market_close_kst"], errors="coerce") <= as_of_kst
    data["calendar_source"] = CALENDAR_SOURCE
    data["calendar_version"] = CALENDAR_VERSION
    return data[
        [
            "session_date",
            "market_open_kst",
            "market_close_kst",
            "is_completed",
            "calendar_source",
            "calendar_version",
        ]
    ].reset_index(drop=True)


def kospi_latest_completed_session(as_of_utc: object) -> pd.Timestamp | None:
    return latest_completed_session(as_of_utc)


def kospi_next_session(date: object) -> pd.Timestamp | None:
    return next_session(date)


def audit_against_frozen_sessions(
    frozen_dates: pd.Series | pd.DatetimeIndex,
    *,
    start: str = "2024-01-01",
    end: str = "2026-07-31",
) -> pd.DataFrame:
    asset = load_krx_calendar_asset()
    sessions = pd.DatetimeIndex(pd.to_datetime(asset["session_date"])).normalize()
    session_set = set(sessions[(sessions >= pd.Timestamp(start)) & (sessions <= pd.Timestamp(end))].strftime("%Y-%m-%d"))
    frozen = pd.DatetimeIndex(pd.to_datetime(frozen_dates)).normalize().unique().sort_values()
    frozen_set = set(d for d in frozen.strftime("%Y-%m-%d") if start <= d <= end)
    rows: list[dict[str, object]] = []
    for key in sorted(session_set | frozen_set):
        in_calendar = key in session_set
        in_frozen = key in frozen_set
        mismatch_type = ""
        if in_calendar and not in_frozen:
            mismatch_type = "CALENDAR_SESSION_BENCHMARK_MISSING"
        elif in_frozen and not in_calendar:
            mismatch_type = "BENCHMARK_SESSION_CALENDAR_MISSING"
        rows.append(
            {
                "session_date": key,
                "in_calendar_asset": in_calendar,
                "in_frozen_benchmark": in_frozen,
                "mismatch_type": mismatch_type,
                "classification": "MATCH" if not mismatch_type else mismatch_type,
                "calendar_source": CALENDAR_SOURCE,
                "calendar_version": CALENDAR_VERSION,
            }
        )
    return pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)
