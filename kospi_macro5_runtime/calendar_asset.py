from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


BASE_ENGINE_CANDIDATES = (
    ("exchange_calendars", "XKRX"),
    ("pandas_market_calendars", "XKRX"),
)


@dataclass(frozen=True)
class CalendarAssetValidation:
    valid: bool
    duplicate_session_count: int
    invalid_session_time_count: int
    timezone_missing_count: int
    coverage_start: str | None
    coverage_end: str | None
    error: str = ""


KST = ZoneInfo("Asia/Seoul")
DEFAULT_CALENDAR_ASSET = Path(__file__).resolve().parents[1] / "kospi_macro5_assets" / "kospi_d1c2a2r_krx_calendar_asset.parquet"
DEFAULT_CALENDAR_CONTRACT = Path(__file__).resolve().parents[1] / "kospi_macro5_assets" / "kospi_d1c2a2r_krx_calendar_contract.json"


def discover_base_calendar_engines() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for package_name, calendar_name in BASE_ENGINE_CANDIDATES:
        spec = importlib.util.find_spec(package_name)
        row: dict[str, Any] = {
            "package": package_name,
            "calendar_name": calendar_name,
            "installed": bool(spec),
            "package_version": None,
            "calendar_available": False,
            "schedule_supported": False,
            "session_open_close_supported": False,
            "error": "",
        }
        if spec is None:
            row["error"] = "PACKAGE_NOT_INSTALLED"
            rows.append(row)
            continue
        try:
            module = importlib.import_module(package_name)
            row["package_version"] = getattr(module, "__version__", "UNKNOWN")
            if package_name == "exchange_calendars":
                cal = module.get_calendar(calendar_name)
                schedule = cal.schedule.loc["2026-07-27":"2026-07-31"]
                row["calendar_available"] = True
                row["schedule_supported"] = not schedule.empty
                row["session_open_close_supported"] = {"market_open", "market_close"}.issubset(set(schedule.columns))
            elif package_name == "pandas_market_calendars":
                cal = module.get_calendar(calendar_name)
                schedule = cal.schedule("2026-07-27", "2026-07-31")
                row["calendar_available"] = True
                row["schedule_supported"] = not schedule.empty
                row["session_open_close_supported"] = {"market_open", "market_close"}.issubset(set(schedule.columns))
        except Exception as exc:  # pragma: no cover - depends on optional external packages
            row["error"] = f"{exc.__class__.__name__}: {exc}"
        rows.append(row)
    return pd.DataFrame(rows)


def base_engine_resolved(status: pd.DataFrame) -> bool:
    if status is None or status.empty:
        return False
    required = ["installed", "calendar_available", "schedule_supported", "session_open_close_supported"]
    if any(col not in status.columns for col in required):
        return False
    return bool(status[required].all(axis=1).any())


def validate_calendar_asset(asset: pd.DataFrame) -> CalendarAssetValidation:
    required = ["session_date", "market_open_kst", "market_close_kst"]
    missing = [col for col in required if col not in asset.columns]
    if missing:
        return CalendarAssetValidation(False, 0, 0, 0, None, None, f"MISSING_COLUMNS:{','.join(missing)}")
    data = asset.copy()
    data["session_date"] = pd.to_datetime(data["session_date"], errors="coerce").dt.normalize()
    open_ts = pd.to_datetime(data["market_open_kst"], errors="coerce")
    close_ts = pd.to_datetime(data["market_close_kst"], errors="coerce")
    duplicate_count = int(data["session_date"].duplicated().sum())
    invalid_time_count = int((open_ts >= close_ts).fillna(True).sum())
    timezone_missing_count = 0
    for col in ["market_open_kst", "market_close_kst"]:
        for value in data[col]:
            ts = pd.Timestamp(value) if not pd.isna(value) else pd.NaT
            if pd.isna(ts) or ts.tzinfo is None:
                timezone_missing_count += 1
    valid = duplicate_count == 0 and invalid_time_count == 0 and timezone_missing_count == 0
    return CalendarAssetValidation(
        valid=valid,
        duplicate_session_count=duplicate_count,
        invalid_session_time_count=invalid_time_count,
        timezone_missing_count=timezone_missing_count,
        coverage_start=None if data["session_date"].isna().all() else data["session_date"].min().strftime("%Y-%m-%d"),
        coverage_end=None if data["session_date"].isna().all() else data["session_date"].max().strftime("%Y-%m-%d"),
    )


def load_krx_calendar_asset(path: str | Path | None = None) -> pd.DataFrame:
    asset_path = Path(path) if path is not None else DEFAULT_CALENDAR_ASSET
    if not asset_path.exists():
        raise FileNotFoundError(f"CALENDAR_ASSET_MISSING:{asset_path}")
    asset = pd.read_parquet(asset_path)
    validation = validate_calendar_asset(asset)
    if not validation.valid:
        raise ValueError(f"CALENDAR_ASSET_INVALID:{validation.error}")
    out = asset.copy()
    out["session_date"] = pd.to_datetime(out["session_date"], errors="coerce").dt.normalize()
    return out.sort_values("session_date").reset_index(drop=True)


def is_session(date: object, calendar_asset: pd.DataFrame | None = None) -> bool:
    asset = load_krx_calendar_asset() if calendar_asset is None else calendar_asset
    target = pd.Timestamp(date).normalize()
    sessions = pd.DatetimeIndex(pd.to_datetime(asset["session_date"]).dt.normalize())
    return bool(target in set(sessions))


def session_open(date: object, calendar_asset: pd.DataFrame | None = None) -> pd.Timestamp:
    asset = load_krx_calendar_asset() if calendar_asset is None else calendar_asset
    target = pd.Timestamp(date).normalize()
    row = asset.loc[pd.to_datetime(asset["session_date"]).dt.normalize().eq(target)]
    if row.empty:
        raise KeyError(f"CALENDAR_NOT_SESSION:{target.strftime('%Y-%m-%d')}")
    return pd.Timestamp(row["market_open_kst"].iloc[0])


def session_close(date: object, calendar_asset: pd.DataFrame | None = None) -> pd.Timestamp:
    asset = load_krx_calendar_asset() if calendar_asset is None else calendar_asset
    target = pd.Timestamp(date).normalize()
    row = asset.loc[pd.to_datetime(asset["session_date"]).dt.normalize().eq(target)]
    if row.empty:
        raise KeyError(f"CALENDAR_NOT_SESSION:{target.strftime('%Y-%m-%d')}")
    return pd.Timestamp(row["market_close_kst"].iloc[0])


def latest_completed_session(as_of_utc: object, calendar_asset: pd.DataFrame | None = None) -> pd.Timestamp | None:
    asset = load_krx_calendar_asset() if calendar_asset is None else calendar_asset
    ts = pd.Timestamp(as_of_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    as_of_kst = ts.tz_convert(KST)
    closes = pd.to_datetime(asset["market_close_kst"], errors="coerce", utc=True).dt.tz_convert(KST)
    completed = asset.loc[closes <= as_of_kst]
    if completed.empty:
        return None
    return pd.Timestamp(completed["session_date"].iloc[-1]).normalize()


def next_session(session_or_date: object, calendar_asset: pd.DataFrame | None = None) -> pd.Timestamp | None:
    asset = load_krx_calendar_asset() if calendar_asset is None else calendar_asset
    target = pd.Timestamp(session_or_date).normalize()
    sessions = pd.to_datetime(asset["session_date"], errors="coerce").dt.normalize()
    future = asset.loc[sessions > target]
    if future.empty:
        return None
    return pd.Timestamp(future["session_date"].iloc[0]).normalize()
