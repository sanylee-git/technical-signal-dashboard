from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_runtime import _source_availability, normalize_daily_merge_key, run_live_runtime
from kosdaq_macro7_runtime.live_sources import SOURCE_SPECS
from kosdaq_macro7_runtime.market_calendar import session_status
from tools.kosdaq_macro7_validate_live_runtime import validate


def _frames(*, include_intraday_market_row: bool = False, stale_vix: bool = False) -> dict[str, pd.DataFrame]:
    dates = pd.to_datetime(["2026-07-24", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"])
    result: dict[str, pd.DataFrame] = {}
    for source_id, spec in SOURCE_SPECS.items():
        source_dates = pd.to_datetime(["2026-07-20"]) if source_id == "vix" and stale_vix else dates
        rows = []
        for index, date in enumerate(source_dates):
            row = {
                "source_id": source_id, "provider": spec.provider, "provider_identifier": spec.provider_identifier,
                "observation_date": date, "publication_date": pd.NaT, "value": float(100 + index),
                "valid": True, "status": "FETCH_OK", "invalid_reason": "", "fetched_at_utc": "2026-08-03T00:00:00+00:00",
                "source_route": "fixture", "error_type": "", "error_message": "",
            }
            if source_id == "kosdaq_ohlcv":
                row.update({"open": 700.0 + index, "high": 710.0 + index, "low": 695.0 + index, "close": 705.0 + index, "volume": 1000 + index})
                row["value"] = row["close"]
            rows.append(row)
        if source_id == "kosdaq_ohlcv" and include_intraday_market_row:
            rows.append({**rows[-1], "observation_date": pd.Timestamp("2026-08-03"), "open": 710.0, "high": 715.0, "low": 705.0, "close": 712.0, "value": 712.0})
        result[source_id] = pd.DataFrame(rows)
    return result


def test_fixture_live_runtime_preserves_frozen_prefix() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), provider_frames=_frames())
    validation = validate(live_result=live)
    assert validation["gate"] == "PASS_KOSDAQ_MACRO7_D2_LIVE_RUNTIME_READY"
    assert sum(validation["prefix_mismatch"].values()) == 0
    assert validation["boundary"] == {"boundary_state_reset_count": 0, "boundary_t1_reset_count": 0}
    assert live["merge"]["frozen_rows_overwritten"] == 0
    assert live["merge"]["duplicate_date_count"] == 0
    assert live["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert live["final_t1_application_count"] == 1
    assert live["provisional_intraday_model_state"] == "NOT_COMPUTED"


def test_intraday_market_row_is_not_treated_as_final() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 3, 2, tzinfo=timezone.utc), provider_frames=_frames(include_intraday_market_row=True))
    assert session_status(datetime(2026, 8, 3, 2, tzinfo=timezone.utc)) == "INTRADAY"
    assert live["merge"]["last_valid_close_date"] == "2026-07-31"
    assert live["merge"]["live_tail_last_date"] == "2026-07-31"


def test_stale_or_missing_source_does_not_become_risk_on() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), provider_frames=_frames(stale_vix=True))
    vix_candidates = [candidate_id for candidate_id, basis in live["core_bases"].items() if "__vix_level__" in candidate_id]
    assert vix_candidates
    assert all(live["core_bases"][candidate_id] is None for candidate_id in vix_candidates)
    assert live["invalid_component_as_risk_on_count"] == 0
    assert (live["snapshot"]["status"] == "UNAVAILABLE").any()


def test_weekend_session_is_not_a_final_krx_session() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 2, 5, tzinfo=timezone.utc), provider_frames=_frames())
    assert session_status(datetime(2026, 8, 2, 5, tzinfo=timezone.utc)) == "NON_SESSION_DAY"
    assert live["merge"]["last_valid_close_date"] == "2026-07-31"


def test_live_runtime_has_no_macro5_or_research_runtime_import() -> None:
    source = "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in [
        "kosdaq_macro7_runtime/live_sources.py", "kosdaq_macro7_runtime/market_calendar.py", "kosdaq_macro7_runtime/live_runtime.py",
    ])
    for forbidden in ["kospi_macro5_runtime", "kospi_macro5_assets", "macro_dashboard_kosdaq", "candidate_metadata.parquet", "outputs/kosdaq/run_"]:
        assert forbidden not in source


def test_source_availability_normalizes_mixed_datetime_units_before_asof_merge() -> None:
    dates = pd.DatetimeIndex(np.array(["2026-07-29", "2026-07-30"], dtype="datetime64[ns]"))
    source = pd.DataFrame(
        {
            "observation_date": np.array(["2026-07-28", "2026-07-29"], dtype="datetime64[s]"),
            "value": [10.0, 11.0],
            "valid": [True, True],
        }
    )

    aligned, _ = _source_availability(source, "vix", dates)

    assert str(normalize_daily_merge_key(source["observation_date"]).dtype) == "datetime64[ns]"
    assert str(aligned["date"].dtype) == "datetime64[ns]"
    assert str(aligned["vix_available_date"].dtype) == "datetime64[ns]"
    assert aligned["vix"].tolist() == [10.0, 11.0]


def test_live_runtime_accepts_provider_frames_with_second_resolution_dates() -> None:
    frames = _frames()
    for frame in frames.values():
        frame["observation_date"] = np.array(
            pd.to_datetime(frame["observation_date"]).dt.strftime("%Y-%m-%d").tolist(),
            dtype="datetime64[s]",
        )

    live = run_live_runtime(
        as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc),
        provider_frames=frames,
    )

    assert validate(live_result=live)["gate"] == "PASS_KOSDAQ_MACRO7_D2_LIVE_RUNTIME_READY"
