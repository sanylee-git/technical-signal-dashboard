from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kospi_macro5_runtime.live_contracts import SOURCE_CONTRACTS as KOSPI_CONTRACTS
from kospi_macro5_runtime.live_sources import normalize_naver_kospi_payload
from nasdaq_macro8_runtime.live_sources import SOURCE_SPECS as NASDAQ_SPECS, fetch_source as fetch_nasdaq_source
from spx_macro9_runtime.live_sources import SOURCE_SPECS as SPX_SPECS, fetch_source as fetch_spx_source


AS_OF = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)


def _ohlcv_frame(*, include_volume: bool, latest_close: float | None) -> pd.DataFrame:
    data = {
        "Open": [100.0, 101.0],
        "High": [101.0, 102.0],
        "Low": [99.0, 100.0],
        "Close": [100.5, latest_close],
    }
    if include_volume:
        data["Volume"] = [1000.0, 1000.0]
    return pd.DataFrame(data, index=pd.to_datetime(["2026-08-25", "2026-08-26"]))


def test_kospi_naver_fallback_payload_keeps_existing_ohlcv_contract() -> None:
    payload = "[['날짜','시가','고가','저가','종가','거래량'],['20260825','100','101','99','100.5','1000'],['20260826','101','102','100','101.5','1100']]"

    output = normalize_naver_kospi_payload(payload, KOSPI_CONTRACTS["kospi_ohlcv"])

    valid = output.loc[output["valid"].astype(bool)]
    assert valid["observation_date"].max() == pd.Timestamp("2026-08-26")
    assert valid["provider"].iloc[-1] == "naver_finance"
    assert valid["provider_series_id"].iloc[-1] == "KOSPI"
    assert "authorized_live_fallback" in valid["source_route"].iloc[-1]


def test_nasdaq_yahoo_retry_recovers_invalid_latest_row(monkeypatch) -> None:
    class FakeTicker:
        def history(self, **_kwargs):
            return _ohlcv_frame(include_volume=True, latest_close=102.0)

    fake_yfinance = types.SimpleNamespace(
        download=lambda *_args, **_kwargs: _ohlcv_frame(include_volume=True, latest_close=None),
        Ticker=lambda *_args, **_kwargs: FakeTicker(),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    output = fetch_nasdaq_source(NASDAQ_SPECS["ndx_ohlcv"], as_of=AS_OF)

    assert output.loc[output["valid"].astype(bool), "observation_date"].max() == pd.Timestamp("2026-08-26")
    assert "authorized_same_provider_retry" in output["source_route"].iloc[0]


def test_spx_yahoo_retry_recovers_invalid_latest_row(monkeypatch) -> None:
    class FakeTicker:
        def history(self, **_kwargs):
            return _ohlcv_frame(include_volume=False, latest_close=102.0)

    fake_yfinance = types.SimpleNamespace(
        download=lambda *_args, **_kwargs: _ohlcv_frame(include_volume=False, latest_close=None),
        Ticker=lambda *_args, **_kwargs: FakeTicker(),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    output = fetch_spx_source(SPX_SPECS["spx_ohlcv"], as_of=AS_OF)

    assert output.loc[output["valid"].astype(bool), "observation_date"].max() == pd.Timestamp("2026-08-26")
    assert "authorized_same_provider_retry" in output["source_route"].iloc[0]
