from __future__ import annotations

import numpy as np
import pandas as pd

from spx_macro9_runtime.frozen_runtime import run_frozen_runtime
from spx_macro9_runtime.live_runtime import FROZEN_CUTOFF, run_live_runtime


def _frame(dates: object, values: object, **extra: object) -> pd.DataFrame:
    output = pd.DataFrame({"observation_date": pd.to_datetime(dates), "value": values, "valid": True})
    for key, value in extra.items():
        output[key] = value
    return output


def _provider_fixture() -> dict[str, pd.DataFrame]:
    frozen = run_frozen_runtime()["panel"].copy()
    frozen["date"] = pd.to_datetime(frozen["date"])
    base = frozen.iloc[-1]
    dates = pd.to_datetime(["2026-08-24", "2026-08-25", "2026-08-26"])
    close = float(base.close)
    frames = {
        "spx_ohlcv": _frame(
            dates, [close * 1.01, close * 1.015, close * 1.02],
            open=[close * 1.005, close * 1.01, close * 1.016],
            high=[close * 1.011, close * 1.017, close * 1.022],
            low=[close, close * 1.008, close * 1.014],
            close=[close * 1.01, close * 1.015, close * 1.02],
        ),
        "equal_weight": _frame(dates, [float(base.equal_weight_price)] * 3),
        "vix": _frame(dates, [float(base.vix)] * 3),
        "vix3m": _frame(dates, [float(base.vix3m)] * 3),
    }
    source_dates = pd.to_datetime(["2026-08-21", "2026-08-24", "2026-08-25"])
    for source, column in (("dfii10", "real_yield_10y"), ("dgs10", "dgs10"), ("t10y2y", "spread_10y2y"), ("t10y3m", "spread_10y3m")):
        frames[source] = _frame(source_dates, [float(base[column])] * 3)
    for source, column in (("dbaa", "hy_raw_proxy"), ("daaa", "ig_raw_proxy")):
        frames[source] = _frame(source_dates, [float(base[column]) + float(base.dgs10)] * 3)
    frames["nfci"] = _frame(pd.to_datetime(["2026-08-19", "2026-08-20", "2026-08-21"]), [float(base.nfci)] * 3)
    return frames


def test_spx_live_runtime_preserves_frozen_prefix_and_appends_only_valid_tail() -> None:
    frozen = run_frozen_runtime()
    live = run_live_runtime(as_of="2026-08-27T12:00:00Z", provider_frames=_provider_fixture())
    assert live["basis_date"] == "2026-08-26"
    assert live["live_tail_row_count"] == 3
    assert live["frozen_rows_overwritten"] == 0
    assert live["proxy_only"] is True
    assert live["direct_oas_used"] is False
    assert live["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert live["final_t1_application_count"] == 1
    expected = frozen["panel"].copy().reset_index(drop=True)
    actual = live["panel"].loc[pd.to_datetime(live["panel"]["date"]).le(FROZEN_CUTOFF)].reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[expected.columns], expected, check_dtype=True)
    pd.testing.assert_frame_equal(live["metrics"], frozen["metrics"], check_dtype=True)
    assert live["snapshot"]["calculable"].all()
    assert live["snapshot"]["basis_date"].eq("2026-08-26").all()


def test_spx_live_runtime_stale_required_source_keeps_confirmed_and_provisional_snapshots() -> None:
    frames = _provider_fixture()
    frames["dgs10"] = frames["dgs10"].iloc[:1].copy()
    live = run_live_runtime(as_of="2026-08-27T12:00:00Z", provider_frames=frames)
    assert live["confirmed_basis_date"] == "2026-08-24"
    assert live["provisional_basis_date"] == "2026-08-26"
    assert live["live_tail_row_count"] == 3
    assert live["confirmed_snapshot"]["availability_status"].eq("CONFIRMED").all()
    assert live["snapshot"]["availability_status"].eq("PROVISIONAL").all()


def test_spx_empty_live_sources_are_explicitly_unavailable_instead_of_confirmed() -> None:
    frames = {source_id: frame.iloc[0:0].copy() for source_id, frame in _provider_fixture().items()}
    live = run_live_runtime(as_of="2026-08-27T12:00:00Z", provider_frames=frames)

    assert live["basis_date"] == "2026-08-21"
    assert live["provisional_status"] == "PROVISIONAL_UNAVAILABLE"
    assert live["provisional_unavailable_reason"]


def test_spx_live_runtime_frozen_core_prefix_matches_stage2_reference() -> None:
    frozen = run_frozen_runtime()
    reference = pd.read_parquet("spx_macro9_assets/frozen/core15_selected_reference_raw_state.parquet")
    dates = pd.to_datetime(frozen["panel"]["date"]).dt.normalize()
    official = (dates >= pd.Timestamp("2008-04-01")) & (dates <= FROZEN_CUTOFF)
    assert np.array_equal(dates[official].to_numpy(), pd.to_datetime(reference["date"]).to_numpy())
    for candidate_id in reference.columns.drop("date"):
        assert np.array_equal(frozen["core"][candidate_id]["raw"][official.to_numpy()], reference[candidate_id].to_numpy(dtype=np.int8))
