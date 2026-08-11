from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kospi_macro5_runtime import page_adapter
from kospi_macro5_runtime.live_contracts import SourceContract


AS_OF_UTC = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _contracts() -> dict[str, SourceContract]:
    return {
        "kospi_ohlcv": SourceContract("kospi_ohlcv", "yahoo", "^KS11", 0, "close", ("kospi_close",)),
        "vix": SourceContract("vix", "fred", "VIXCLS", 1, "value", ("vix_safe",)),
        "us_10y_yield": SourceContract("us_10y_yield", "fred", "DGS10", 1, "value", ("us_10y_yield",)),
        "nfci": SourceContract("nfci", "fred", "NFCI", 3, "value", ("credit_stress_safe",), frequency="weekly"),
    }


def _install_source_loader_stubs(monkeypatch, contracts: dict[str, SourceContract], selected_attempt: int = 1) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(page_adapter, "SOURCE_CONTRACTS", contracts)

    def fake_fetch_with_optional_bypass(contract, **kwargs):
        calls.append(
            {
                "source_id": contract.source_id,
                "cache_mode": "workflow",
                "fetcher_is_runtime": kwargs.get("fetcher") is page_adapter.fetch_source,
            }
        )
        frame = pd.DataFrame(
            {
                "source_id": [contract.source_id],
                "provider": [contract.provider],
                "provider_series_id": [contract.provider_series_id],
                "observation_date": [pd.Timestamp("2026-08-10")],
                "value": [1.0],
                "valid": [True],
                "status": ["IMPLEMENTED_FETCH_OK"],
                "source_route": [f"{contract.provider};cache_mode=NORMAL"],
            }
        )
        attempts = [
            {
                "source_id": contract.source_id,
                "attempt_number": selected_attempt,
                "cache_mode": "NORMAL",
                "freshness_status": "FRESH",
            }
        ]
        meta = {
            "selected_attempt": selected_attempt,
            "selected_reason": "INITIAL_ATTEMPT",
            "retry_executed": False,
            "retry_freshness_status": "NOT_EXECUTED",
        }
        return frame, attempts, meta

    def fake_evaluate(contract, frame, **kwargs):
        return SimpleNamespace(
            final_freshness_status="FRESH",
            actual_latest_observation_date="2026-08-10",
            actual_latest_available_date="2026-08-11",
            actual_latest_krx_aligned_date="2026-08-11",
            expected_latest_observation_date="2026-08-10",
            expected_latest_available_date="2026-08-11",
            expected_latest_krx_aligned_date="2026-08-11",
            lag_krx_sessions=0,
        )

    def fake_normalize(contract, frame, **kwargs):
        return frame.copy(), {
            "raw_latest_observation_date": "2026-08-10",
            "selected_latest_observation_date": "2026-08-10",
            "allowed_partial_row_count": 0,
            "excluded_partial_row_count": 0,
            "kospi_partial_daily_allowed": contract.source_id == "kospi_ohlcv",
            "kospi_latest_row_final": True if contract.source_id == "kospi_ohlcv" else None,
            "kospi_live_observation_type": "completed_daily" if contract.source_id == "kospi_ohlcv" else "",
        }

    monkeypatch.setattr(page_adapter, "fetch_with_optional_bypass", fake_fetch_with_optional_bypass)
    monkeypatch.setattr(page_adapter, "evaluate_source_freshness", fake_evaluate)
    monkeypatch.setattr(page_adapter, "normalize_provider_dates_for_freshness", fake_normalize)
    return calls


def test_fred_source_parallel_loader_preserves_canonical_order_and_contract(monkeypatch) -> None:
    contracts = _contracts()
    calls = _install_source_loader_stubs(monkeypatch, contracts)

    selected_frames, source_rows = page_adapter._load_source_frames(
        as_of_utc=AS_OF_UTC,
        sessions=pd.DatetimeIndex(pd.to_datetime(["2026-08-11"])),
        latest_krx=pd.Timestamp("2026-08-11"),
        latest_kospi_live=pd.Timestamp("2026-08-11"),
    )

    assert list(selected_frames) == list(contracts)
    assert [row["source_id"] for row in source_rows] == list(contracts)
    assert [call["source_id"] for call in calls].count("kospi_ohlcv") == 1
    assert sorted(call["source_id"] for call in calls if call["source_id"] != "kospi_ohlcv") == ["nfci", "us_10y_yield", "vix"]
    assert all(call["fetcher_is_runtime"] for call in calls)
    assert all(row["selected_attempt"] == 1 for row in source_rows)
    assert all(row["freshness_status"] == "FRESH" for row in source_rows)


def test_fred_source_parallel_loader_uses_max_workers_four(monkeypatch) -> None:
    contracts = _contracts()
    _install_source_loader_stubs(monkeypatch, contracts)
    observed_workers: list[int | None] = []

    class ImmediateFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class FakeExecutor:
        def __init__(self, max_workers=None):
            observed_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, fn, *args, **kwargs):
            return ImmediateFuture(fn(*args, **kwargs))

    monkeypatch.setattr(page_adapter, "ThreadPoolExecutor", FakeExecutor)

    page_adapter._load_source_frames(
        as_of_utc=AS_OF_UTC,
        sessions=pd.DatetimeIndex(pd.to_datetime(["2026-08-11"])),
        latest_krx=pd.Timestamp("2026-08-11"),
        latest_kospi_live=pd.Timestamp("2026-08-11"),
    )

    assert observed_workers == [4]


def test_fred_source_parallel_loader_propagates_unexpected_failure(monkeypatch) -> None:
    contracts = _contracts()
    monkeypatch.setattr(page_adapter, "SOURCE_CONTRACTS", contracts)

    def fake_load_one_source_frame(*, source_id, contract, **_kwargs):
        if source_id == "us_10y_yield":
            raise RuntimeError("unexpected source workflow failure")
        return pd.DataFrame({"source_id": [source_id]}), {"source_id": source_id}

    monkeypatch.setattr(page_adapter, "_load_one_source_frame", fake_load_one_source_frame)

    with pytest.raises(RuntimeError, match="unexpected source workflow failure"):
        page_adapter._load_source_frames(
            as_of_utc=AS_OF_UTC,
            sessions=pd.DatetimeIndex(pd.to_datetime(["2026-08-11"])),
            latest_krx=pd.Timestamp("2026-08-11"),
            latest_kospi_live=pd.Timestamp("2026-08-11"),
        )
