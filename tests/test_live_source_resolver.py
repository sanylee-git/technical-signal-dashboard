from __future__ import annotations

import pandas as pd

from live_source_resolver import exact_date_spread, resolve_aligned_sources


def _candidate(dates: list[str], values: list[float], *, valid: list[bool] | None = None) -> pd.DataFrame:
    return pd.DataFrame({
        "observation_date": pd.to_datetime(dates),
        "value": values,
        "valid": [True] * len(dates) if valid is None else valid,
    })


def test_resolver_uses_fresher_source_even_when_secondary() -> None:
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-09-28", "2026-09-29"]))
    resolved, status = resolve_aligned_sources(
        dates,
        {"PRIMARY": _candidate(["2026-09-28"], [4.0]), "SECONDARY": _candidate(["2026-09-29"], [5.0])},
        primary_source="PRIMARY", lag=0, calendar_mode="business_day", tolerance=0.01,
    )

    assert resolved.iloc[-1]["selected_source"] == "SECONDARY"
    assert resolved.iloc[-1]["value"] == 5.0
    assert status["latest_observation_date"] == "2026-09-29"


def test_same_date_discrepancy_uses_primary_and_logs_alert() -> None:
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-09-28"]))
    resolved, status = resolve_aligned_sources(
        dates,
        {"PRIMARY": _candidate(["2026-09-28"], [4.0]), "SECONDARY": _candidate(["2026-09-28"], [4.5])},
        primary_source="PRIMARY", lag=0, calendar_mode="business_day", tolerance=0.1,
    )

    assert resolved.iloc[0]["selected_source"] == "PRIMARY"
    assert resolved.iloc[0]["selection_reason"] == "SAME_DATE_DISCREPANCY_PRIMARY_USED"
    assert bool(resolved.iloc[0]["discrepancy_flag"])
    assert status["discrepancy_count"] == 1


def test_invalid_primary_falls_back_and_derived_spread_requires_exact_dates() -> None:
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-09-28", "2026-09-29"]))
    resolved, _status = resolve_aligned_sources(
        dates,
        {"PRIMARY": _candidate(["2026-09-28"], [1.0], valid=[False]), "SECONDARY": _candidate(["2026-09-29"], [3.0])},
        primary_source="PRIMARY", lag=0, calendar_mode="business_day", tolerance=0.0,
    )
    spread = exact_date_spread(
        _candidate(["2026-09-28", "2026-09-29"], [5.0, 6.0]),
        _candidate(["2026-09-29"], [2.0]),
        "DERIVED",
    )

    assert resolved.iloc[-1]["selected_source"] == "SECONDARY"
    assert spread[["observation_date", "value"]].to_dict("records") == [{"observation_date": pd.Timestamp("2026-09-29"), "value": 4.0}]
