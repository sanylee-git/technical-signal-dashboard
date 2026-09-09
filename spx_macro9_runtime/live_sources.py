"""S&P Macro9-only source adapters; no other market runtime is imported."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Callable

import pandas as pd
import requests


COMMON = ["source_id", "provider", "provider_identifier", "observation_date", "value", "valid", "status", "fetched_at_utc", "source_route", "error_type", "error_message"]


@dataclass(frozen=True)
class LiveSourceSpec:
    source_id: str
    provider: str
    provider_identifier: str
    lag_market_sessions: int
    cadence: str


SOURCE_SPECS = {
    "spx_ohlcv": LiveSourceSpec("spx_ohlcv", "yahoo", "^GSPC", 0, "daily"),
    "equal_weight": LiveSourceSpec("equal_weight", "yahoo", "^SP500EW", 0, "daily"),
    "vix": LiveSourceSpec("vix", "yahoo", "^VIX", 0, "daily"),
    "vix3m": LiveSourceSpec("vix3m", "cboe", "VIX3M", 0, "daily"),
    "dfii10": LiveSourceSpec("dfii10", "fred", "DFII10", 1, "daily"),
    "dgs10": LiveSourceSpec("dgs10", "fred", "DGS10", 1, "daily"),
    "t10y2y": LiveSourceSpec("t10y2y", "fred", "T10Y2Y", 1, "daily"),
    "t10y3m": LiveSourceSpec("t10y3m", "fred", "T10Y3M", 1, "daily"),
    "dbaa": LiveSourceSpec("dbaa", "fred", "DBAA", 1, "daily"),
    "daaa": LiveSourceSpec("daaa", "fred", "DAAA", 1, "daily"),
    "nfci": LiveSourceSpec("nfci", "fred", "NFCI", 3, "weekly"),
}


def _stamp(as_of: datetime | pd.Timestamp | None) -> str:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    return (value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")).isoformat()


def _empty(spec: LiveSourceSpec, kind: str, message: str, *, as_of: object, route: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "source_id": spec.source_id, "provider": spec.provider, "provider_identifier": spec.provider_identifier,
        "observation_date": pd.NaT, "value": pd.NA, "valid": False, "status": "TEMPORARY_FETCH_FAILURE",
        "fetched_at_utc": _stamp(as_of), "source_route": route, "error_type": kind, "error_message": message,
    }])


def _finalize(spec: LiveSourceSpec, frame: pd.DataFrame, *, as_of: object, route: str, ohlc: bool = False) -> pd.DataFrame:
    output = frame.copy()
    output["observation_date"] = pd.to_datetime(output["observation_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    output["value"] = pd.to_numeric(output["value"], errors="coerce")
    output["valid"] = output["observation_date"].notna() & output["value"].notna()
    if ohlc:
        required = ["open", "high", "low", "close"]
        output[required] = output[required].apply(pd.to_numeric, errors="coerce")
        output["valid"] &= output[required].notna().all(axis=1) & output["open"].gt(0) & output["low"].gt(0) & output["close"].gt(0)
        output["valid"] &= output["high"].ge(output[["open", "low", "close"]].max(axis=1)) & output["low"].le(output[["open", "high", "close"]].min(axis=1))
    output["source_id"] = spec.source_id
    output["provider"] = spec.provider
    output["provider_identifier"] = spec.provider_identifier
    output["status"] = output["valid"].map(lambda ok: "FETCH_OK" if ok else "INVALID_VALUE")
    output["fetched_at_utc"] = _stamp(as_of)
    output["source_route"] = route
    output["error_type"] = ""
    output["error_message"] = ""
    columns = COMMON + (["open", "high", "low", "close"] if ohlc else [])
    return output[columns].sort_values("observation_date").drop_duplicates("observation_date", keep="last").reset_index(drop=True)


def normalize_yahoo(frame: pd.DataFrame, spec: LiveSourceSpec, *, as_of: object) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty(spec, "EMPTY_RESPONSE", "Yahoo response empty", as_of=as_of, route="yfinance")
    data = frame.copy().reset_index()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(column[0]).lower().replace(" ", "_") for column in data.columns]
    else:
        data.columns = [str(column).lower().replace(" ", "_") for column in data.columns]
    if "date" not in data and "index" in data:
        data = data.rename(columns={"index": "date"})
    if spec.source_id == "spx_ohlcv":
        if not {"date", "open", "high", "low", "close"}.issubset(data):
            return _empty(spec, "SCHEMA_ERROR", "Yahoo OHLC schema missing", as_of=as_of, route="yfinance")
        out = data[["date", "open", "high", "low", "close"]].rename(columns={"date": "observation_date"})
        out["value"] = out["close"]
        return _finalize(spec, out, as_of=as_of, route=f"yf.download({spec.provider_identifier})", ohlc=True)
    if not {"date", "close"}.issubset(data):
        return _empty(spec, "SCHEMA_ERROR", "Yahoo close schema missing", as_of=as_of, route="yfinance")
    return _finalize(spec, data[["date", "close"]].rename(columns={"date": "observation_date", "close": "value"}), as_of=as_of, route=f"yf.download({spec.provider_identifier})")


def normalize_fred(payload: str, spec: LiveSourceSpec, *, as_of: object) -> pd.DataFrame:
    data = pd.read_csv(StringIO(payload))
    date = "observation_date" if "observation_date" in data else "DATE"
    if date not in data or spec.provider_identifier not in data:
        return _empty(spec, "SCHEMA_ERROR", "FRED schema missing", as_of=as_of, route="fredgraph.csv")
    return _finalize(spec, pd.DataFrame({"observation_date": data[date], "value": data[spec.provider_identifier].replace(".", pd.NA)}), as_of=as_of, route="fredgraph.csv")


def _latest_valid_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame is None or frame.empty or "valid" not in frame or "observation_date" not in frame:
        return None
    dates = pd.to_datetime(frame.loc[frame["valid"].astype(bool), "observation_date"], errors="coerce").dropna()
    return None if dates.empty else pd.Timestamp(dates.max()).normalize()


def _latest_observation_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame is None or frame.empty or "observation_date" not in frame:
        return None
    dates = pd.to_datetime(frame["observation_date"], errors="coerce").dropna()
    return None if dates.empty else pd.Timestamp(dates.max()).normalize()


def _latest_completed_us_session(as_of: object) -> pd.Timestamp | None:
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    try:
        import pandas_market_calendars as mcal

        schedule = mcal.get_calendar("NYSE").schedule(
            start_date=(now.tz_convert("America/New_York").date() - pd.Timedelta(days=14)),
            end_date=now.tz_convert("America/New_York").date(),
        )
        completed = schedule.loc[schedule["market_close"].le(now)]
        return None if completed.empty else pd.Timestamp(completed.index[-1]).normalize()
    except Exception:
        local = now.tz_convert("America/New_York")
        session = pd.Timestamp(local.date())
        if local.weekday() >= 5 or local.time() < pd.Timestamp("16:00").time():
            session -= pd.offsets.BDay(1)
        while session.weekday() >= 5:
            session -= pd.offsets.BDay(1)
        return session.normalize()


def _needs_yahoo_retry(frame: pd.DataFrame, as_of: object) -> bool:
    latest_valid = _latest_valid_date(frame)
    latest_observation = _latest_observation_date(frame)
    if latest_valid is None:
        return True
    if latest_observation is not None and latest_observation > latest_valid:
        return True
    expected = _latest_completed_us_session(as_of)
    return expected is not None and latest_valid < expected


def _fetch_yahoo_with_authorized_retry(spec: LiveSourceSpec, *, as_of: object) -> pd.DataFrame:
    import yfinance as yf

    start, end = _window(as_of)
    primary = normalize_yahoo(
        yf.download(spec.provider_identifier, start=start, end=end, interval="1d", auto_adjust=False, progress=False, threads=False),
        spec,
        as_of=as_of,
    )
    if not _needs_yahoo_retry(primary, as_of):
        return primary
    retry = normalize_yahoo(
        yf.Ticker(spec.provider_identifier).history(start=start, end=end, interval="1d", auto_adjust=False),
        spec,
        as_of=as_of,
    )
    primary_date = _latest_valid_date(primary)
    retry_date = _latest_valid_date(retry)
    if retry_date is not None and (primary_date is None or retry_date >= primary_date):
        retry["source_route"] = retry["source_route"].astype(str) + ";authorized_same_provider_retry"
        return retry
    return primary


def _window(as_of: object) -> tuple[str, str]:
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    return "2026-08-01", (now.tz_convert("America/New_York").normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_source(spec: LiveSourceSpec, *, as_of: object = None) -> pd.DataFrame:
    try:
        if spec.provider == "yahoo":
            return _fetch_yahoo_with_authorized_retry(spec, as_of=as_of)
        if spec.provider == "cboe":
            response = requests.get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv", timeout=20)
            response.raise_for_status()
            data = pd.read_csv(StringIO(response.text))
            return _finalize(spec, data.rename(columns={"DATE": "observation_date", "Date": "observation_date", "CLOSE": "value", "Close": "value"}), as_of=as_of, route="cboe_vix3m_history")
        response = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec.provider_identifier}", timeout=20)
        response.raise_for_status()
        return normalize_fred(response.text, spec, as_of=as_of)
    except Exception as exc:  # pragma: no cover - provider behavior
        return _empty(spec, exc.__class__.__name__, str(exc), as_of=as_of, route=spec.provider)


def fetch_all_sources(*, as_of: object = None, fetcher: Callable[[LiveSourceSpec], pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    return {name: (fetcher(spec) if fetcher else fetch_source(spec, as_of=as_of)) for name, spec in SOURCE_SPECS.items()}
