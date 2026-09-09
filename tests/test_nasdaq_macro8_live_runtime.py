from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd
from pandas.testing import assert_frame_equal


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nasdaq_macro8_runtime.frozen_runtime import run_frozen_runtime
from nasdaq_macro8_runtime.live_runtime import FROZEN_CUTOFF, run_live_runtime
from nasdaq_macro8_runtime.live_sources import SOURCE_SPECS
from nasdaq_macro8_runtime.presentation_payload import build_presentation_payload


def _frame(source_id: str, dates: list[str], values: list[float]) -> pd.DataFrame:
    spec = SOURCE_SPECS[source_id]
    return pd.DataFrame({
        "source_id": source_id,
        "provider": spec.provider,
        "provider_identifier": spec.provider_identifier,
        "observation_date": pd.to_datetime(dates),
        "value": values,
        "valid": True,
        "status": "FIXTURE_OK",
        "fetched_at_utc": "2026-08-26T00:00:00+00:00",
        "source_route": "fixture",
        "error_type": "",
        "error_message": "",
    })


def _live_frames() -> dict[str, pd.DataFrame]:
    market_dates = ["2026-08-24", "2026-08-25"]
    result = {
        "ndx_ohlcv": _frame("ndx_ohlcv", market_dates, [29400.0, 29500.0]),
        "ndxe_close": _frame("ndxe_close", market_dates, [10400.0, 10420.0]),
    }
    result["ndx_ohlcv"]["open"] = [29350.0, 29450.0]
    result["ndx_ohlcv"]["high"] = [29450.0, 29550.0]
    result["ndx_ohlcv"]["low"] = [29300.0, 29400.0]
    result["ndx_ohlcv"]["close"] = [29400.0, 29500.0]
    result["ndx_ohlcv"]["volume"] = [1000.0, 1000.0]
    for source_id in SOURCE_SPECS:
        if source_id in result:
            continue
        result[source_id] = _frame(
            source_id,
            ["2026-08-19"] if source_id == "nfci" else ["2026-08-21", "2026-08-24"],
            [-0.55] if source_id == "nfci" else [10.0, 11.0],
        )
    return result


def test_live_tail_preserves_frozen_prefix_and_advances_current_basis() -> None:
    frozen = run_frozen_runtime()
    live = run_live_runtime(as_of=datetime(2026, 8, 26, tzinfo=timezone.utc), provider_frames=_live_frames())

    prefix = live["panel"].loc[lambda frame: frame["date"].le(FROZEN_CUTOFF), frozen["panel"].columns]
    assert_frame_equal(prefix.reset_index(drop=True), frozen["panel"].reset_index(drop=True), check_dtype=False)
    assert live["runtime_mode"] == "LIVE_TAIL"
    assert live["network_access"] is False
    assert live["basis_date"] == "2026-08-25"
    assert live["live_tail_row_count"] == 2
    assert live["frozen_rows_overwritten"] == 0
    assert live["snapshot"]["calculable"].all()
    assert live["snapshot"]["basis_date"].eq("2026-08-25").all()
    assert live["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert live["final_t1_application_count"] == 1


def test_live_payload_keeps_official_backtest_metrics_frozen_and_extends_charts() -> None:
    frozen = run_frozen_runtime()
    live = run_live_runtime(as_of=datetime(2026, 8, 26, tzinfo=timezone.utc), provider_frames=_live_frames())
    frozen_payload = build_presentation_payload(frozen)
    live_payload = build_presentation_payload(live)

    assert live_payload["runtime_mode"] == "LIVE_TAIL"
    assert live_payload["presentation_contract"] == "nasdaq_macro8_live_presentation_payload_v1"
    assert live_payload["benchmark_history"]["date"].max().strftime("%Y-%m-%d") == "2026-08-25"
    assert live_payload["candidate_history"]["date"].max().strftime("%Y-%m-%d") == "2026-08-25"
    assert_frame_equal(
        live_payload["frozen_display_metrics"].sort_values(["candidate_id", "window"]).reset_index(drop=True),
        frozen_payload["frozen_display_metrics"].sort_values(["candidate_id", "window"]).reset_index(drop=True),
    )
    assert_frame_equal(
        live_payload["benchmark_display_metrics"].sort_values("window").reset_index(drop=True),
        frozen_payload["benchmark_display_metrics"].sort_values("window").reset_index(drop=True),
    )


def test_stale_or_missing_live_source_keeps_frozen_cutoff_without_rewriting_history() -> None:
    frozen = run_frozen_runtime()
    frames = _live_frames()
    frames["dgs10"] = frames["dgs10"].iloc[0:0].copy()
    live = run_live_runtime(as_of=datetime(2026, 8, 26, tzinfo=timezone.utc), provider_frames=frames)

    assert live["basis_date"] == "2026-08-21"
    assert live["provisional_status"] == "PROVISIONAL_UNAVAILABLE"
    assert live["live_tail_row_count"] == 0
    assert_frame_equal(live["panel"].reset_index(drop=True), frozen["panel"].reset_index(drop=True), check_dtype=False)


def test_empty_live_sources_are_explicitly_unavailable_instead_of_confirmed() -> None:
    frames = {source_id: frame.iloc[0:0].copy() for source_id, frame in _live_frames().items()}
    live = run_live_runtime(as_of=datetime(2026, 8, 26, tzinfo=timezone.utc), provider_frames=frames)

    assert live["basis_date"] == "2026-08-21"
    assert live["provisional_status"] == "PROVISIONAL_UNAVAILABLE"
    assert live["provisional_unavailable_reason"]


def test_stale_corporate_yields_carry_completed_proxy_without_mixing_observation_dates() -> None:
    frames = _live_frames()
    frames["dbaa"] = frames["dbaa"].iloc[:1].copy()
    frames["daaa"] = frames["daaa"].iloc[:1].copy()

    live = run_live_runtime(as_of=datetime(2026, 8, 26, tzinfo=timezone.utc), provider_frames=frames)
    panel = live["panel"].set_index("date")
    before = panel.loc[pd.Timestamp("2026-08-24"), "hy_proxy"]
    carried = panel.loc[pd.Timestamp("2026-08-25")]

    assert live["confirmed_basis_date"] == "2026-08-24"
    assert live["provisional_basis_date"] == "2026-08-25"
    assert carried["dbaa_source_observation_date"] != carried["dgs10_source_observation_date"]
    assert carried["hy_proxy"] == before
