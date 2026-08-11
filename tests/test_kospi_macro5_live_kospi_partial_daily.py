from __future__ import annotations

from datetime import datetime, timezone
import sys
import types

import pandas as pd

from kospi_macro5_runtime.freshness import evaluate_source_freshness
from kospi_macro5_runtime.krx_calendar import kospi_latest_allowed_live_session, kospi_latest_completed_session
from kospi_macro5_runtime.live_contracts import SOURCE_CONTRACTS
from kospi_macro5_runtime.live_sources import fetch_yahoo, normalize_yahoo_ohlcv_payload
from kospi_macro5_runtime.provider_dates import normalize_provider_dates_for_freshness


INTRADAY_UTC = datetime(2026, 8, 11, 2, 0, tzinfo=timezone.utc)


def _raw_ks11_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": ["2026-08-10", "2026-08-11", "2026-08-12"],
            "Open": [3200.0, 3210.0, 3220.0],
            "High": [3210.0, 3225.0, 3230.0],
            "Low": [3190.0, 3205.0, 3215.0],
            "Close": [3205.0, 3220.0, 3222.0],
            "Volume": [0, 0, 0],
        }
    )


def test_kospi_live_session_uses_kst_current_session_before_close() -> None:
    assert kospi_latest_completed_session(INTRADAY_UTC).strftime("%Y-%m-%d") == "2026-08-10"
    assert kospi_latest_allowed_live_session(INTRADAY_UTC).strftime("%Y-%m-%d") == "2026-08-11"


def test_kospi_provider_date_keeps_current_partial_row_and_drops_future() -> None:
    contract = SOURCE_CONTRACTS["kospi_ohlcv"]
    raw = normalize_yahoo_ohlcv_payload(_raw_ks11_frame(), contract, route="fixture", as_of_utc=INTRADAY_UTC)

    selected, audit = normalize_provider_dates_for_freshness(
        contract,
        raw,
        expected_latest_observation_date="2026-08-11",
        latest_completed_krx_session="2026-08-10",
        latest_allowed_kospi_session="2026-08-11",
    )

    dates = pd.to_datetime(selected.loc[selected["valid"].astype(bool), "observation_date"]).dt.strftime("%Y-%m-%d")
    assert dates.tolist() == ["2026-08-10", "2026-08-11"]
    assert audit["allowed_partial_row_count"] == 1
    assert audit["excluded_partial_row_count"] == 0
    assert audit["excluded_future_row_count"] == 1
    assert audit["kospi_partial_daily_allowed"] is True
    assert audit["kospi_latest_row_final"] is False
    assert audit["kospi_live_observation_type"] == "intraday_partial"


def test_kospi_freshness_treats_allowed_partial_session_as_fresh() -> None:
    contract = SOURCE_CONTRACTS["kospi_ohlcv"]
    raw = normalize_yahoo_ohlcv_payload(_raw_ks11_frame().iloc[:2], contract, route="fixture", as_of_utc=INTRADAY_UTC)
    sessions = pd.DatetimeIndex(pd.to_datetime(["2026-08-10", "2026-08-11"]))

    evaluation = evaluate_source_freshness(
        contract,
        raw,
        as_of_utc=INTRADAY_UTC,
        krx_sessions=sessions,
        latest_completed_krx=pd.Timestamp("2026-08-10"),
        latest_allowed_kospi_session=pd.Timestamp("2026-08-11"),
    )

    assert evaluation.final_freshness_status == "FRESH"
    assert evaluation.expected_latest_observation_date == "2026-08-11"
    assert evaluation.actual_latest_observation_date == "2026-08-11"
    assert evaluation.actual_latest_available_date == "2026-08-11"
    assert evaluation.lag_krx_sessions == 0


def test_kospi_latest_row_rejects_flat_previous_close_as_stale() -> None:
    contract = SOURCE_CONTRACTS["kospi_ohlcv"]
    frame = pd.DataFrame(
        {
            "Date": ["2026-08-10", "2026-08-11"],
            "Open": [6299.66, 6299.66],
            "High": [6305.00, 6299.66],
            "Low": [6280.00, 6299.66],
            "Close": [6299.66, 6299.66],
            "Volume": [0, 0],
        }
    )

    raw = normalize_yahoo_ohlcv_payload(frame, contract, route="fixture", as_of_utc=INTRADAY_UTC)

    latest = raw.loc[pd.to_datetime(raw["observation_date"]).dt.strftime("%Y-%m-%d").eq("2026-08-11")].iloc[0]
    assert latest["valid"] is False or latest["valid"] == False
    assert latest["status"] == "INVALID_VALUE"
    assert "stale" in str(latest["invalid_reason"]).lower()
    valid_dates = pd.to_datetime(raw.loc[raw["valid"].astype(bool), "observation_date"]).dt.strftime("%Y-%m-%d")
    assert valid_dates.tolist() == ["2026-08-10"]


def test_kospi_yahoo_fetch_uses_dashboard_start_end_daily_route(monkeypatch) -> None:
    contract = SOURCE_CONTRACTS["kospi_ohlcv"]
    calls = {}

    def fake_download(ticker, **kwargs):
        calls["ticker"] = ticker
        calls["kwargs"] = kwargs
        return pd.DataFrame(
            {
                "Date": ["2026-08-10", "2026-08-11"],
                "Open": [6299.66, 6240.06],
                "High": [6305.00, 6405.81],
                "Low": [6280.00, 6213.78],
                "Close": [6299.66, 6345.53],
                "Volume": [0, 0],
            }
        )

    fake_yf = types.SimpleNamespace(download=fake_download)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    out = fetch_yahoo(contract, cache_mode="NORMAL", as_of_utc=INTRADAY_UTC)

    assert calls["ticker"] == "^KS11"
    assert calls["kwargs"]["start"] == "2026-01-04"
    assert calls["kwargs"]["end"] == "2026-08-12"
    assert calls["kwargs"]["interval"] == "1d"
    assert "period" not in calls["kwargs"]
    assert out["source_route"].iloc[0].startswith("yf.download(start=2026-01-04,end=2026-08-12,interval=1d)")
    assert pd.to_datetime(out.loc[out["valid"].astype(bool), "observation_date"]).max().strftime("%Y-%m-%d") == "2026-08-11"
