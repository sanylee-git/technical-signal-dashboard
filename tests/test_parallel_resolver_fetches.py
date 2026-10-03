from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import kosdaq_macro7_runtime.live_sources as kosdaq_sources
import nasdaq_macro8_runtime.live_sources as nasdaq_sources
import spx_macro9_runtime.live_sources as spx_sources
from live_source_resolver import exact_date_spread, resolve_aligned_sources


ADAPTERS = [
    pytest.param("S&P2", spx_sources, id="spx2"),
    pytest.param("NASDAQ", nasdaq_sources, id="nasdaq"),
    pytest.param("KOSDAQ", kosdaq_sources, id="kosdaq"),
]
AS_OF = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
DATES = pd.bdate_range("2026-09-21", periods=8)
STALE_DIRECT_IDS = {
    "t10y2y", "t10y3m",
    "resolver_t10y2y", "resolver_t10y3m", "resolver_cboe_vix3m",
}


def _fixture_frame(spec, *, dates: pd.DatetimeIndex = DATES) -> pd.DataFrame:
    if spec.source_id in STALE_DIRECT_IDS:
        dates = dates[:-1]
    base_value = float(sum(map(ord, spec.source_id)) % 20 + 10)
    frame = pd.DataFrame({
        "source_id": spec.source_id,
        "provider": spec.provider,
        "provider_identifier": spec.provider_identifier,
        "observation_date": dates,
        "value": [base_value + i for i in range(len(dates))],
        "valid": True,
        "status": "FIXTURE_OK",
        "fetched_at_utc": AS_OF.isoformat(),
        "source_route": "injected",
        "error_type": "",
        "error_message": "",
    })
    if spec.source_id in {"spx_ohlcv", "ndx_ohlcv", "kosdaq_ohlcv"}:
        frame["open"] = frame["value"]
        frame["high"] = frame["value"] + 1
        frame["low"] = frame["value"] - 1
        frame["close"] = frame["value"]
    return frame


def _fetcher(spec):
    return _fixture_frame(spec)


def _sequential_fetch(adapter, fetcher):
    return {
        source_id: fetcher(spec)
        for source_id, spec in {**adapter.SOURCE_SPECS, **adapter.RESOLVER_SOURCE_SPECS}.items()
    }


def _selection_outputs(tab: str, frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    if tab == "S&P2":
        pairs = {
            "10Y-2Y": ("t10y2y", exact_date_spread(frames["dgs10"], frames["resolver_dgs2"], "DERIVED_DGS10_MINUS_DGS2")),
            "10Y-3M": ("t10y3m", exact_date_spread(frames["dgs10"], frames["resolver_dgs3mo"], "DERIVED_DGS10_MINUS_DGS3MO")),
            "VIX3M": ("vix3m", frames["resolver_vxvcls"]),
        }
        source_names = {"10Y-2Y": "FRED_T10Y2Y", "10Y-3M": "FRED_T10Y3M", "VIX3M": "CBOE_VIX3M"}
        secondary_names = {"10Y-2Y": "DERIVED_DGS10_MINUS_DGS2", "10Y-3M": "DERIVED_DGS10_MINUS_DGS3MO", "VIX3M": "FRED_VXVCLS"}
    elif tab == "NASDAQ":
        pairs = {
            "10Y-2Y": ("resolver_t10y2y", exact_date_spread(frames["dgs10"], frames["dgs2"], "DERIVED_DGS10_MINUS_DGS2")),
            "10Y-3M": ("resolver_t10y3m", exact_date_spread(frames["dgs10"], frames["dgs3mo"], "DERIVED_DGS10_MINUS_DGS3MO")),
            "VIX3M": ("resolver_cboe_vix3m", frames["vxvcls"]),
        }
        source_names = {"10Y-2Y": "FRED_T10Y2Y", "10Y-3M": "FRED_T10Y3M", "VIX3M": "CBOE_VIX3M"}
        secondary_names = {"10Y-2Y": "DERIVED_DGS10_MINUS_DGS2", "10Y-3M": "DERIVED_DGS10_MINUS_DGS3MO", "VIX3M": "FRED_VXVCLS"}
    else:
        pairs = {
            "10Y-2Y": ("resolver_t10y2y", exact_date_spread(frames["us_10y_yield"], frames["us_2y_yield"], "DERIVED_DGS10_MINUS_DGS2")),
            "10Y-3M": ("resolver_t10y3m", exact_date_spread(frames["us_10y_yield"], frames["us_3m_yield"], "DERIVED_DGS10_MINUS_DGS3MO")),
            "VIX3M": ("resolver_cboe_vix3m", frames["vix3m"]),
        }
        source_names = {"10Y-2Y": "FRED_T10Y2Y", "10Y-3M": "FRED_T10Y3M", "VIX3M": "CBOE_VIX3M"}
        secondary_names = {"10Y-2Y": "DERIVED_DGS10_MINUS_DGS2", "10Y-3M": "DERIVED_DGS10_MINUS_DGS3MO", "VIX3M": "FRED_VXVCLS"}

    results = {}
    for logical, (primary_id, secondary) in pairs.items():
        primary = frames[primary_id]
        if tab == "S&P2" and logical == "VIX3M":
            primary = frames["vix3m"].iloc[:-1].copy()
        if tab == "NASDAQ" and logical == "VIX3M":
            primary = frames["resolver_cboe_vix3m"]
        if tab == "KOSDAQ" and logical == "VIX3M":
            primary = frames["resolver_cboe_vix3m"]
        output, _status = resolve_aligned_sources(
            DATES,
            {source_names[logical]: primary, secondary_names[logical]: secondary},
            primary_source=source_names[logical],
            lag=0,
            calendar_mode="business_day",
            tolerance=1e-8 if logical.startswith("10Y") else 0.0,
        )
        results[logical] = output
    return results


@pytest.mark.parametrize("tab,adapter", ADAPTERS)
def test_parallel_fetch_preserves_frames_and_three_resolver_selections(tab, adapter):
    sequential = _sequential_fetch(adapter, _fetcher)
    parallel = adapter.fetch_all_sources(as_of=AS_OF, fetcher=_fetcher)

    assert list(parallel) == list(sequential)
    for source_id in sequential:
        assert_frame_equal(parallel[source_id], sequential[source_id])
    before = _selection_outputs(tab, sequential)
    after = _selection_outputs(tab, parallel)
    for logical in ("VIX3M", "10Y-2Y", "10Y-3M"):
        assert_frame_equal(after[logical], before[logical])
        assert after[logical].iloc[-1]["selected_source"] != ""
        assert after[logical].iloc[-1]["selection_reason"] == "SECONDARY_FRESHER"


@pytest.mark.parametrize("tab,adapter", ADAPTERS)
@pytest.mark.parametrize("failure_count", [1, 2, 3])
def test_resolver_fetch_exceptions_are_isolated(tab, adapter, failure_count):
    failed_ids = list(adapter.RESOLVER_SOURCE_SPECS)[:failure_count]

    def fetcher(spec):
        if spec.source_id in failed_ids:
            raise TimeoutError("injected resolver timeout")
        return _fixture_frame(spec)

    frames = adapter.fetch_all_sources(as_of=AS_OF, fetcher=fetcher)
    for source_id in failed_ids:
        assert not frames[source_id]["valid"].astype(bool).any()
        assert "TIMEOUT" in str(frames[source_id]["error_type"].iloc[0]).upper()
    for source_id in set(adapter.RESOLVER_SOURCE_SPECS) - set(failed_ids):
        assert frames[source_id]["valid"].astype(bool).all()


@pytest.mark.parametrize("tab,adapter", ADAPTERS)
def test_three_delayed_resolver_fetches_run_in_parallel(tab, adapter):
    delays = {source_id: 0.20 + (index * 0.03) for index, source_id in enumerate(adapter.RESOLVER_SOURCE_SPECS)}

    def delayed_fetcher(spec):
        if spec.source_id in delays:
            time.sleep(delays[spec.source_id])
        return _fixture_frame(spec)

    start = time.perf_counter()
    sequential = _sequential_fetch(adapter, delayed_fetcher)
    sequential_seconds = time.perf_counter() - start

    start = time.perf_counter()
    parallel = adapter.fetch_all_sources(as_of=AS_OF, fetcher=delayed_fetcher)
    parallel_seconds = time.perf_counter() - start

    assert parallel_seconds < sequential_seconds * 0.75
    for source_id in sequential:
        assert_frame_equal(parallel[source_id], sequential[source_id])


@pytest.mark.parametrize("tab,adapter", ADAPTERS)
def test_injected_timeout_isolated_while_other_resolver_fetches_finish(tab, adapter):
    slow_timeout_id = next(iter(adapter.RESOLVER_SOURCE_SPECS))
    completion_order: list[str] = []

    def delayed_fetcher(spec):
        if spec.source_id == slow_timeout_id:
            time.sleep(0.30)
            completion_order.append(spec.source_id)
            raise TimeoutError("injected 20-second provider timeout")
        time.sleep(0.02)
        completion_order.append(spec.source_id)
        return _fixture_frame(spec)

    frames = adapter.fetch_all_sources(as_of=AS_OF, fetcher=delayed_fetcher)

    assert completion_order.index(slow_timeout_id) > max(
        completion_order.index(source_id)
        for source_id in adapter.RESOLVER_SOURCE_SPECS
        if source_id != slow_timeout_id
    )
    assert not frames[slow_timeout_id]["valid"].astype(bool).any()
    assert all(
        frames[source_id]["valid"].astype(bool).all()
        for source_id in adapter.RESOLVER_SOURCE_SPECS
        if source_id != slow_timeout_id
    )
