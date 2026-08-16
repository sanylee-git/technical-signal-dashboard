"""Independent KOSDAQ/Macro source fetchers for Macro7 Live runtime."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Callable

import pandas as pd
import requests


COMMON_COLUMNS = [
    "source_id", "provider", "provider_identifier", "observation_date", "publication_date",
    "value", "valid", "status", "invalid_reason", "fetched_at_utc", "source_route",
    "error_type", "error_message",
]
OHLC_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class LiveSourceSpec:
    source_id: str
    provider: str
    provider_identifier: str
    lag_bdays: int
    cadence: str
    required_by_indicator_families: tuple[str, ...]
    fallback_provider: str | None = None
    fallback_identifier: str | None = None


SOURCE_SPECS: dict[str, LiveSourceSpec] = {
    "kosdaq_ohlcv": LiveSourceSpec("kosdaq_ohlcv", "naver_finance", "KOSDAQ", 0, "daily", ("kosdaq_index_level", "kosdaq_bollinger", "kosdaq_hv", "kosdaq_natr", "kosdaq_rsi"), "yahoo", "^KQ11"),
    "usdkrw": LiveSourceSpec("usdkrw", "yahoo", "KRW=X", 1, "daily", ("usdkrw_level",)),
    "vix": LiveSourceSpec("vix", "fred", "VIXCLS", 1, "daily", ("vix_level", "vix_spread", "global_credit_stress")),
    "vix3m": LiveSourceSpec("vix3m", "fred", "VXVCLS", 1, "daily", ("vix_spread",)),
    "us_10y_real_yield": LiveSourceSpec("us_10y_real_yield", "fred", "DFII10", 1, "daily", ("us_10y_real_yield_level",)),
    "us_10y_yield": LiveSourceSpec("us_10y_yield", "fred", "DGS10", 1, "daily", ("us_10y_2y_spread", "us_10y_3m_spread", "us_10y_slope", "us_hy_oas_level", "us_ig_oas_level", "global_credit_stress")),
    "us_2y_yield": LiveSourceSpec("us_2y_yield", "fred", "DGS2", 1, "daily", ("us_10y_2y_spread",)),
    "us_3m_yield": LiveSourceSpec("us_3m_yield", "fred", "DGS3MO", 1, "daily", ("us_10y_3m_spread",)),
    "us_baa_corp_yield": LiveSourceSpec("us_baa_corp_yield", "fred", "DBAA", 1, "daily", ("us_hy_oas_level", "global_credit_stress")),
    "us_aaa_corp_yield": LiveSourceSpec("us_aaa_corp_yield", "fred", "DAAA", 1, "daily", ("us_ig_oas_level",)),
    "nfci": LiveSourceSpec("nfci", "fred", "NFCI", 3, "weekly", ("global_credit_stress",)),
}


def source_specs_payload() -> list[dict[str, object]]:
    return [asdict(spec) for spec in SOURCE_SPECS.values()]


def _fetched_at(as_of: datetime | pd.Timestamp | None) -> str:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return value.tz_convert("UTC").isoformat()


def _empty(spec: LiveSourceSpec, status: str, error_type: str = "", error_message: str = "", *, route: str = "", as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    row = {
        "source_id": spec.source_id, "provider": spec.provider, "provider_identifier": spec.provider_identifier,
        "observation_date": pd.NaT, "publication_date": pd.NaT, "value": pd.NA, "valid": False,
        "status": status, "invalid_reason": error_message, "fetched_at_utc": _fetched_at(as_of),
        "source_route": route, "error_type": error_type, "error_message": error_message,
    }
    return pd.DataFrame([row], columns=COMMON_COLUMNS + (OHLC_COLUMNS if spec.source_id == "kosdaq_ohlcv" else []))


def _finalize(spec: LiveSourceSpec, data: pd.DataFrame, invalid: pd.Series, *, route: str, as_of: datetime | pd.Timestamp | None) -> pd.DataFrame:
    out = data.copy()
    out["source_id"] = spec.source_id
    out["provider"] = spec.provider
    out["provider_identifier"] = spec.provider_identifier
    out["publication_date"] = pd.NaT
    out["valid"] = ~invalid.astype(bool)
    out["status"] = out["valid"].map(lambda value: "FETCH_OK" if value else "INVALID_VALUE")
    out["invalid_reason"] = out["valid"].map(lambda value: "" if value else "invalid source row")
    out["fetched_at_utc"] = _fetched_at(as_of)
    out["source_route"] = route
    out["error_type"] = ""
    out["error_message"] = ""
    out["observation_date"] = pd.to_datetime(out["observation_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    out = out.drop_duplicates(["source_id", "observation_date"], keep="last")
    columns = COMMON_COLUMNS + [column for column in OHLC_COLUMNS if column in out]
    return out[columns].sort_values("observation_date").reset_index(drop=True)


def normalize_naver_kosdaq_payload(payload: str, spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    try:
        rows = ast.literal_eval(payload.strip())
        data = pd.DataFrame(rows[1:], columns=rows[0])
        out = pd.DataFrame({
            "observation_date": pd.to_datetime(data["날짜"], format="%Y%m%d", errors="coerce"),
            "open": pd.to_numeric(data["시가"], errors="coerce"),
            "high": pd.to_numeric(data["고가"], errors="coerce"),
            "low": pd.to_numeric(data["저가"], errors="coerce"),
            "close": pd.to_numeric(data["종가"], errors="coerce"),
            "volume": pd.to_numeric(data["거래량"], errors="coerce"),
        })
    except Exception as exc:
        return _empty(spec, "SCHEMA_ERROR", exc.__class__.__name__, str(exc), route="naver_siseJson", as_of=as_of)
    out["value"] = out["close"]
    invalid = out["observation_date"].isna() | out[["open", "high", "low", "close"]].isna().any(axis=1) | (out["open"] <= 0) | (out["high"] < out[["open", "close", "low"]].max(axis=1)) | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    return _finalize(spec, out, invalid, route="naver_siseJson", as_of=as_of)


def normalize_yahoo_payload(frame: pd.DataFrame, spec: LiveSourceSpec, *, route: str, as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty(spec, "TEMPORARY_FETCH_FAILURE", "EMPTY_RESPONSE", "Yahoo response empty", route=route, as_of=as_of)
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
    if spec.source_id == "kosdaq_ohlcv":
        needed = {"date", "open", "high", "low", "close"}
        if not needed.issubset(data.columns):
            return _empty(spec, "SCHEMA_ERROR", "MISSING_COLUMNS", str(sorted(needed.difference(data.columns))), route=route, as_of=as_of)
        out = pd.DataFrame({"observation_date": pd.to_datetime(data["date"], errors="coerce"), "open": pd.to_numeric(data["open"], errors="coerce"), "high": pd.to_numeric(data["high"], errors="coerce"), "low": pd.to_numeric(data["low"], errors="coerce"), "close": pd.to_numeric(data["close"], errors="coerce"), "volume": pd.to_numeric(data.get("volume"), errors="coerce")})
        out["value"] = out["close"]
        invalid = out["observation_date"].isna() | out[["open", "high", "low", "close"]].isna().any(axis=1) | (out["open"] <= 0) | (out["high"] < out[["open", "close", "low"]].max(axis=1)) | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    else:
        if not {"date", "close"}.issubset(data.columns):
            return _empty(spec, "SCHEMA_ERROR", "MISSING_COLUMNS", "date/close", route=route, as_of=as_of)
        out = pd.DataFrame({"observation_date": pd.to_datetime(data["date"], errors="coerce"), "value": pd.to_numeric(data["close"], errors="coerce")})
        invalid = out["observation_date"].isna() | out["value"].isna()
    return _finalize(spec, out, invalid, route=route, as_of=as_of)


def normalize_fred_payload(payload: str, spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None = None) -> pd.DataFrame:
    try:
        data = pd.read_csv(StringIO(payload))
        date_column = "observation_date" if "observation_date" in data.columns else "DATE"
        if date_column not in data.columns or spec.provider_identifier not in data.columns:
            raise ValueError("missing observation_date/series column")
        out = pd.DataFrame({"observation_date": pd.to_datetime(data[date_column], errors="coerce"), "value": pd.to_numeric(data[spec.provider_identifier].replace(".", pd.NA), errors="coerce")})
    except Exception as exc:
        return _empty(spec, "SCHEMA_ERROR", exc.__class__.__name__, str(exc), route="fredgraph.csv", as_of=as_of)
    return _finalize(spec, out, out["observation_date"].isna() | out["value"].isna(), route="fredgraph.csv", as_of=as_of)


def _window(as_of: datetime | pd.Timestamp | None, days: int = 260) -> tuple[str, str]:
    now = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    end = now.tz_convert("Asia/Seoul").normalize() + pd.Timedelta(days=1)
    return (end - pd.Timedelta(days=days)).strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_source(spec: LiveSourceSpec, *, as_of: datetime | pd.Timestamp | None = None, use_fallback: bool = False) -> pd.DataFrame:
    provider = spec.fallback_provider if use_fallback else spec.provider
    identifier = spec.fallback_identifier if use_fallback else spec.provider_identifier
    try:
        if provider == "naver_finance":
            start, end = _window(as_of)
            response = requests.get("https://api.finance.naver.com/siseJson.naver", params={"symbol": identifier, "requestType": "1", "startTime": start.replace("-", ""), "endTime": end.replace("-", ""), "timeframe": "day"}, timeout=20)
            response.raise_for_status()
            return normalize_naver_kosdaq_payload(response.text, spec, as_of=as_of)
        if provider == "yahoo":
            import yfinance as yf
            start, end = _window(as_of)
            raw = yf.download(identifier, start=start, end=end, interval="1d", auto_adjust=False, progress=False, threads=False)
            return normalize_yahoo_payload(raw, spec, route=f"yf.download({identifier})", as_of=as_of)
        if provider == "fred":
            response = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={identifier}", timeout=20)
            response.raise_for_status()
            return normalize_fred_payload(response.text, spec, as_of=as_of)
        return _empty(spec, "CONTRACT_BLOCKED", "UNKNOWN_PROVIDER", provider, as_of=as_of)
    except Exception as exc:  # pragma: no cover - external provider behavior
        return _empty(spec, "TEMPORARY_FETCH_FAILURE", exc.__class__.__name__, str(exc), route=str(provider), as_of=as_of)


def fetch_all_sources(*, as_of: datetime | pd.Timestamp | None = None, fetcher: Callable[[LiveSourceSpec], pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for source_id, spec in SOURCE_SPECS.items():
        primary = fetcher(spec) if fetcher is not None else fetch_source(spec, as_of=as_of)
        if source_id == "kosdaq_ohlcv" and not primary.get("valid", pd.Series(False, index=primary.index)).astype(bool).any():
            fallback = fetch_source(spec, as_of=as_of, use_fallback=True)
            if fallback.get("valid", pd.Series(False, index=fallback.index)).astype(bool).any():
                fallback["provider"] = "yahoo"
                fallback["provider_identifier"] = "^KQ11"
                fallback["source_route"] = fallback["source_route"].astype(str) + ";authorized_fallback"
                frames[source_id] = fallback
                continue
        frames[source_id] = primary
    return frames
