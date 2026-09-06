"""NASDAQ Macro8-only provider adapters for the Core15 live tail."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Callable

import pandas as pd
import requests


COMMON_COLUMNS = [
    "source_id", "provider", "provider_identifier", "observation_date", "value", "valid",
    "status", "fetched_at_utc", "source_route", "error_type", "error_message",
]
OHLC_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class LiveSourceSpec:
    source_id: str
    provider: str
    provider_identifier: str
    lag_market_sessions: int
    cadence: str


SOURCE_SPECS: dict[str, LiveSourceSpec] = {
    "ndx_ohlcv": LiveSourceSpec("ndx_ohlcv", "yahoo", "^NDX", 0, "daily"),
    "ndxe_close": LiveSourceSpec("ndxe_close", "yahoo", "^NDXE", 0, "daily"),
    "vixcls": LiveSourceSpec("vixcls", "fred", "VIXCLS", 1, "daily"),
    "vxvcls": LiveSourceSpec("vxvcls", "fred", "VXVCLS", 1, "daily"),
    "dfii10": LiveSourceSpec("dfii10", "fred", "DFII10", 1, "daily"),
    "dgs10": LiveSourceSpec("dgs10", "fred", "DGS10", 1, "daily"),
    "dgs2": LiveSourceSpec("dgs2", "fred", "DGS2", 1, "daily"),
    "dgs3mo": LiveSourceSpec("dgs3mo", "fred", "DGS3MO", 1, "daily"),
    "dbaa": LiveSourceSpec("dbaa", "fred", "DBAA", 1, "daily"),
    "daaa": LiveSourceSpec("daaa", "fred", "DAAA", 1, "daily"),
    "nfci": LiveSourceSpec("nfci", "fred", "NFCI", 3, "weekly"),
}


def _fetched_at(as_of: datetime | pd.Timestamp | None) -> str:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return value.tz_convert("UTC").isoformat()


def _empty(spec: LiveSourceSpec, status: str, error_type: str, error_message: str, *, as_of: datetime | pd.Timestamp | None, route: str) -> pd.DataFrame:
    row = {
        "source_id": spec.source_id, "provider": spec.provider, "provider_identifier": spec.provider_identifier,
        "observation_date": pd.NaT, "value": pd.NA, "valid": False, "status": status,
        "fetched_at_utc": _fetched_at(as_of), "source_route": route,
        "error_type": error_type, "error_message": error_message,
    }
    return pd.DataFrame([row], columns=COMMON_COLUMNS + (OHLC_COLUMNS if spec.source_id == "ndx_ohlcv" else []))


def _finalize(spec: LiveSourceSpec, frame: pd.DataFrame, invalid: pd.Series, *, as_of: datetime | pd.Timestamp | None, route: str) -> pd.DataFrame:
    out = frame.copy()
    out["source_id"] = spec.source_id
    out["provider"] = spec.provider
    out["provider_identifier"] = spec.provider_identifier
    out["valid"] = ~invalid.astype(bool)
    out["status"] = out["valid"].map(lambda ok: "FETCH_OK" if ok else "INVALID_VALUE")
    out["fetched_at_utc"] = _fetched_at(as_of)
    out["source_route"] = route
    out["error_type"] = ""
    out["error_message"] = ""
    dates = pd.to_datetime(out["observation_date"], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    out["observation_date"] = dates.dt.normalize()
    return out.drop_duplicates(["source_id", "observation_date"], keep="last")[COMMON_COLUMNS + [column for column in OHLC_COLUMNS if column in out]].sort_values("observation_date").reset_index(drop=True)


def normalize_yahoo(frame: pd.DataFrame, spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None, route: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty(spec, "TEMPORARY_FETCH_FAILURE", "EMPTY_RESPONSE", "Yahoo response empty", as_of=as_of, route=route)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(column[0]).lower().replace(" ", "_") for column in data.columns]
    else:
        data.columns = [str(column).lower().replace(" ", "_") for column in data.columns]
    if "date" not in data.columns:
        data = data.reset_index()
        data.columns = [str(column).lower().replace(" ", "_") for column in data.columns]
    if "date" not in data.columns and "index" in data.columns:
        data = data.rename(columns={"index": "date"})
    if spec.source_id == "ndx_ohlcv":
        required = {"date", "open", "high", "low", "close"}
        if not required.issubset(data.columns):
            return _empty(spec, "SCHEMA_ERROR", "MISSING_COLUMNS", str(sorted(required.difference(data.columns))), as_of=as_of, route=route)
        out = pd.DataFrame({
            "observation_date": pd.to_datetime(data["date"], errors="coerce"),
            "open": pd.to_numeric(data["open"], errors="coerce"),
            "high": pd.to_numeric(data["high"], errors="coerce"),
            "low": pd.to_numeric(data["low"], errors="coerce"),
            "close": pd.to_numeric(data["close"], errors="coerce"),
            "volume": pd.to_numeric(data.get("volume"), errors="coerce"),
        })
        out["value"] = out["close"]
        invalid = out["observation_date"].isna() | out[["open", "high", "low", "close"]].isna().any(axis=1)
        invalid |= (out["open"] <= 0) | (out["high"] < out[["open", "close", "low"]].max(axis=1)) | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    else:
        if not {"date", "close"}.issubset(data.columns):
            return _empty(spec, "SCHEMA_ERROR", "MISSING_COLUMNS", "date/close", as_of=as_of, route=route)
        out = pd.DataFrame({"observation_date": pd.to_datetime(data["date"], errors="coerce"), "value": pd.to_numeric(data["close"], errors="coerce")})
        invalid = out["observation_date"].isna() | out["value"].isna()
    return _finalize(spec, out, invalid, as_of=as_of, route=route)


def normalize_fred(payload: str, spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None, route: str) -> pd.DataFrame:
    try:
        data = pd.read_csv(StringIO(payload))
        date_column = "observation_date" if "observation_date" in data.columns else "DATE"
        if date_column not in data.columns or spec.provider_identifier not in data.columns:
            raise ValueError("missing observation_date/series column")
        out = pd.DataFrame({
            "observation_date": pd.to_datetime(data[date_column], errors="coerce"),
            "value": pd.to_numeric(data[spec.provider_identifier].replace(".", pd.NA), errors="coerce"),
        })
    except Exception as exc:
        return _empty(spec, "SCHEMA_ERROR", exc.__class__.__name__, str(exc), as_of=as_of, route=route)
    return _finalize(spec, out, out["observation_date"].isna() | out["value"].isna(), as_of=as_of, route=route)


def _window(as_of: datetime | pd.Timestamp | None) -> tuple[str, str]:
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    end = now.tz_convert("America/New_York").normalize() + pd.Timedelta(days=1)
    start = pd.Timestamp("2026-08-01")
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_source(spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    try:
        if spec.provider == "yahoo":
            import yfinance as yf

            start, end = _window(as_of)
            raw = yf.download(spec.provider_identifier, start=start, end=end, interval="1d", auto_adjust=False, progress=False, threads=False)
            return normalize_yahoo(raw, spec, as_of=as_of, route=f"yf.download({spec.provider_identifier})")
        response = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec.provider_identifier}", timeout=20)
        response.raise_for_status()
        return normalize_fred(response.text, spec, as_of=as_of, route="fredgraph.csv")
    except Exception as exc:  # pragma: no cover - external provider behaviour
        return _empty(spec, "TEMPORARY_FETCH_FAILURE", exc.__class__.__name__, str(exc), as_of=as_of, route=spec.provider)


def fetch_all_sources(*, as_of: datetime | pd.Timestamp | None = None, fetcher: Callable[[LiveSourceSpec], pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    return {source_id: (fetcher(spec) if fetcher is not None else fetch_source(spec, as_of=as_of)) for source_id, spec in SOURCE_SPECS.items()}
