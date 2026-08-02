from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import requests

from .live_contracts import SourceContract


COMMON_COLUMNS = [
    "source_id",
    "provider",
    "provider_series_id",
    "observation_date",
    "publication_date",
    "publication_date_status",
    "value",
    "valid",
    "status",
    "invalid_reason",
    "fetched_at_utc",
    "source_route",
    "revision_mode",
    "error_type",
    "error_message",
]

OHLC_COLUMNS = ["open", "high", "low", "close", "volume"]


def _fetched_at(as_of_utc: datetime | None = None) -> str:
    if as_of_utc is not None:
        return as_of_utc.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _empty_result(
    contract: SourceContract,
    status: str,
    error_type: str = "",
    error_message: str = "",
    *,
    route: str = "",
    as_of_utc: datetime | None = None,
) -> pd.DataFrame:
    cols = COMMON_COLUMNS + (OHLC_COLUMNS if contract.provider == "yahoo" and contract.source_id == "kospi_ohlcv" else [])
    return pd.DataFrame(
        [
            {
                "source_id": contract.source_id,
                "provider": contract.provider,
                "provider_series_id": contract.provider_series_id,
                "observation_date": pd.NaT,
                "publication_date": pd.NaT,
                "publication_date_status": "NOT_AVAILABLE",
                "value": pd.NA,
                "valid": False,
                "status": status,
                "invalid_reason": error_message,
                "fetched_at_utc": _fetched_at(as_of_utc),
                "source_route": route,
                "revision_mode": "LATEST_AVAILABLE_HISTORY",
                "error_type": error_type,
                "error_message": error_message,
            }
        ],
        columns=cols,
    )


def normalize_yahoo_ohlcv_payload(frame: pd.DataFrame, contract: SourceContract, *, route: str = "fixture", as_of_utc: datetime | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_result(contract, "TEMPORARY_FETCH_FAILURE", "EMPTY_RESPONSE", "Yahoo response empty", route=route, as_of_utc=as_of_utc)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(col[0]).lower().replace(" ", "_") for col in data.columns]
    else:
        data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]
    if "date" not in data.columns:
        data = data.reset_index()
        data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]
    if "date" not in data.columns and "index" in data.columns:
        data = data.rename(columns={"index": "date"})
    rename = {"adj_close": "adj_close"}
    data = data.rename(columns=rename)
    required = ["date", "open", "high", "low", "close"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        return _empty_result(contract, "SCHEMA_ERROR", "MISSING_COLUMNS", f"missing columns: {missing}", route=route, as_of_utc=as_of_utc)
    out = pd.DataFrame()
    out["observation_date"] = pd.to_datetime(data["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(data[col], errors="coerce") if col in data.columns else pd.NA
    out["value"] = pd.to_numeric(out["close"], errors="coerce")
    invalid = (
        out["observation_date"].isna()
        | out[["open", "high", "low", "close"]].isna().any(axis=1)
        | (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    )
    return _finalize(contract, out, route, invalid, as_of_utc=as_of_utc)


def normalize_yahoo_close_payload(frame: pd.DataFrame, contract: SourceContract, *, route: str = "fixture", as_of_utc: datetime | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_result(contract, "TEMPORARY_FETCH_FAILURE", "EMPTY_RESPONSE", "Yahoo response empty", route=route, as_of_utc=as_of_utc)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(col[0]).lower().replace(" ", "_") for col in data.columns]
    else:
        data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]
    data = data.reset_index() if "date" not in data.columns else data
    data.columns = [str(col).lower().replace(" ", "_") for col in data.columns]
    if "date" not in data.columns and "index" in data.columns:
        data = data.rename(columns={"index": "date"})
    if "date" not in data.columns or "close" not in data.columns:
        return _empty_result(contract, "SCHEMA_ERROR", "MISSING_COLUMNS", "date/close missing", route=route, as_of_utc=as_of_utc)
    out = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(data["date"], errors="coerce").dt.tz_localize(None).dt.normalize(),
            "value": pd.to_numeric(data["close"], errors="coerce"),
        }
    )
    return _finalize(contract, out, route, out["observation_date"].isna() | out["value"].isna(), as_of_utc=as_of_utc)


def normalize_fred_csv_payload(payload: str | pd.DataFrame, contract: SourceContract, *, route: str = "fixture", as_of_utc: datetime | None = None) -> pd.DataFrame:
    if isinstance(payload, pd.DataFrame):
        data = payload.copy()
    else:
        data = pd.read_csv(StringIO(payload))
    data.columns = [str(col).strip() for col in data.columns]
    if "DATE" not in data.columns and "date" in data.columns:
        data = data.rename(columns={"date": "DATE"})
    if "DATE" not in data.columns and "observation_date" in data.columns:
        data = data.rename(columns={"observation_date": "DATE"})
    if contract.provider_series_id not in data.columns:
        return _empty_result(contract, "SCHEMA_ERROR", "MISSING_SERIES_COLUMN", f"{contract.provider_series_id} missing", route=route, as_of_utc=as_of_utc)
    raw_value = data[contract.provider_series_id].replace(".", pd.NA)
    out = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(data["DATE"], errors="coerce").dt.normalize(),
            "value": pd.to_numeric(raw_value, errors="coerce"),
        }
    )
    return _finalize(contract, out, route, out["observation_date"].isna() | out["value"].isna(), as_of_utc=as_of_utc)


def _finalize(contract: SourceContract, out: pd.DataFrame, route: str, invalid: pd.Series, *, as_of_utc: datetime | None = None) -> pd.DataFrame:
    result = out.copy()
    result["source_id"] = contract.source_id
    result["provider"] = contract.provider
    result["provider_series_id"] = contract.provider_series_id
    result["publication_date"] = pd.NaT
    result["publication_date_status"] = "NOT_AVAILABLE"
    result["valid"] = ~invalid.astype(bool)
    result["status"] = result["valid"].map(lambda ok: "IMPLEMENTED_FETCH_OK" if ok else "INVALID_VALUE")
    result["invalid_reason"] = result["valid"].map(lambda ok: "" if ok else "invalid date/value/OHLC")
    result["fetched_at_utc"] = _fetched_at(as_of_utc)
    result["source_route"] = route
    result["revision_mode"] = "LATEST_AVAILABLE_HISTORY"
    result["error_type"] = ""
    result["error_message"] = ""
    result = result.drop_duplicates(["source_id", "observation_date"], keep=False)
    cols = COMMON_COLUMNS + [col for col in OHLC_COLUMNS if col in result.columns]
    return result[cols].sort_values("observation_date").reset_index(drop=True)


def fetch_yahoo(
    contract: SourceContract,
    *,
    period: str = "6mo",
    cache_mode: str = "NORMAL",
    bypass_token: str | None = None,
    as_of_utc: datetime | None = None,
) -> pd.DataFrame:
    try:
        import yfinance as yf

        route_suffix = f";cache_mode={cache_mode}"
        if cache_mode == "BYPASS" and bypass_token:
            route_suffix += f";bypass={bypass_token}"
        if cache_mode == "BYPASS":
            raw = yf.Ticker(contract.provider_series_id).history(period=period, auto_adjust=False)
            base_route = f"yf.Ticker.history(period={period})"
        else:
            raw = yf.download(contract.provider_series_id, period=period, progress=False, auto_adjust=False, threads=False)
            base_route = f"yf.download(period={period})"
        if contract.source_id == "kospi_ohlcv":
            return normalize_yahoo_ohlcv_payload(raw, contract, route=f"{base_route}{route_suffix}", as_of_utc=as_of_utc)
        return normalize_yahoo_close_payload(raw, contract, route=f"{base_route}{route_suffix}", as_of_utc=as_of_utc)
    except Exception as exc:  # pragma: no cover - depends on network
        return _empty_result(contract, "TEMPORARY_FETCH_FAILURE", exc.__class__.__name__, str(exc), route=f"yf.download(period={period});cache_mode={cache_mode}", as_of_utc=as_of_utc)


def fetch_fred(
    contract: SourceContract,
    *,
    cache_mode: str = "NORMAL",
    bypass_token: str | None = None,
    as_of_utc: datetime | None = None,
) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={contract.provider_series_id}"
    route = "fredgraph.csv"
    params: dict[str, str] = {}
    headers: dict[str, str] = {}
    if cache_mode == "BYPASS" and bypass_token:
        params["_kospi_macro5_bypass"] = bypass_token
        headers["Cache-Control"] = "no-cache"
        route += f";cache_mode=BYPASS;bypass={bypass_token}"
    else:
        route += ";cache_mode=NORMAL"
    try:
        session = requests.Session()
        response = session.get(url, timeout=20, params=params, headers=headers)
        response.raise_for_status()
        return normalize_fred_csv_payload(response.text, contract, route=route, as_of_utc=as_of_utc)
    except Exception as exc:  # pragma: no cover - depends on network
        return _empty_result(contract, "TEMPORARY_FETCH_FAILURE", exc.__class__.__name__, str(exc), route=route, as_of_utc=as_of_utc)


def fetch_source(
    contract: SourceContract,
    *,
    cache_mode: str = "NORMAL",
    bypass_token: str | None = None,
    as_of_utc: datetime | None = None,
) -> pd.DataFrame:
    if contract.provider == "yahoo":
        return fetch_yahoo(contract, cache_mode=cache_mode, bypass_token=bypass_token, as_of_utc=as_of_utc)
    if contract.provider == "fred":
        return fetch_fred(contract, cache_mode=cache_mode, bypass_token=bypass_token, as_of_utc=as_of_utc)
    return _empty_result(contract, "CONTRACT_BLOCKED", "UNKNOWN_PROVIDER", contract.provider, as_of_utc=as_of_utc)
