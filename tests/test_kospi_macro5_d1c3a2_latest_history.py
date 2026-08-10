from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from kospi_macro5_runtime.engine import D1C1Context
from kospi_macro5_runtime.page_adapter import build_selected_component_signal_history, load_macro5_live_page_data


FIXED_AS_OF_UTC = datetime(2026, 8, 2, 11, 16, tzinfo=timezone.utc)
EXPECTED_LATEST_SESSION = "2026-07-31"
EXPECTED_LIVE_TAIL = {"2026-07-29", "2026-07-30", "2026-07-31"}


def _dates(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")


def test_macro5_live_page_data_extends_full_history_to_latest_completed_session() -> None:
    data = load_macro5_live_page_data(FIXED_AS_OF_UTC)

    assert data["expected_latest_krx_session"] == EXPECTED_LATEST_SESSION
    assert data["sources_count"] == 11
    assert data["sources_reachable_count"] == 11

    core = data["core15_component_history"]
    candidate = data["candidate_signal_history"]
    child = data["child_combo1_history"]
    display_components = pd.concat(
        [
            build_selected_component_signal_history(data, str(candidate_id))
            for candidate_id in candidate["candidate_id"].drop_duplicates()
        ],
        ignore_index=True,
    )
    benchmark = data["benchmark_close_history"]

    assert core["component_id"].nunique() == 47
    assert child["combo1_id"].nunique() == 17
    assert candidate["candidate_id"].nunique() == 9
    assert candidate.groupby("model_type")["candidate_id"].nunique().to_dict() == {"combo1": 4, "combo2": 5}
    assert "component_signal_history" not in data
    assert data["component_signal_history_mode"] == "selected_detail_only"

    assert _dates(core).max() == EXPECTED_LATEST_SESSION
    assert _dates(candidate).max() == EXPECTED_LATEST_SESSION
    assert _dates(child).max() == EXPECTED_LATEST_SESSION
    assert _dates(display_components).max() == EXPECTED_LATEST_SESSION
    assert _dates(benchmark).max() == EXPECTED_LATEST_SESSION

    assert EXPECTED_LIVE_TAIL.issubset(set(_dates(candidate)))
    assert EXPECTED_LIVE_TAIL.issubset(set(_dates(display_components)))
    assert EXPECTED_LIVE_TAIL.issubset(set(_dates(benchmark)))

    assert int(core.duplicated(["component_id", "date"]).sum()) == 0
    assert int(candidate.duplicated(["candidate_id", "date"]).sum()) == 0
    assert int(child.duplicated(["combo1_id", "date"]).sum()) == 0
    assert int(display_components.duplicated(["parent_candidate_id", "component_id", "date"]).sum()) == 0
    assert int(benchmark.duplicated(["date"]).sum()) == 0


def test_macro5_live_snapshot_matches_history_last_rows() -> None:
    data = load_macro5_live_page_data(FIXED_AS_OF_UTC)
    snapshot = pd.DataFrame(data["candidate_rows"]).sort_values("candidate_id").reset_index(drop=True)
    candidate = data["candidate_signal_history"].copy()
    last = candidate.sort_values("date").groupby("candidate_id").tail(1).reset_index(drop=True)
    compare = snapshot.merge(last, on="candidate_id", suffixes=("_snapshot", "_history"))

    assert len(snapshot) == 9
    assert len(compare) == 9
    assert int(snapshot["calculable"].astype(bool).sum()) == 9
    assert int(snapshot["freshness_qualified"].astype(bool).sum()) == 9
    assert int(snapshot.loc[snapshot["calculable"].astype(bool), "raw_risk_state"].fillna(0).astype(int).sum()) == 9
    assert int((compare["basis_date"].astype(str) != pd.to_datetime(compare["date"]).dt.strftime("%Y-%m-%d")).sum()) == 0

    for column in ["raw_risk_state", "t1_position", "active_count"]:
        assert int((compare[f"{column}_snapshot"].astype(str) != compare[f"{column}_history"].astype(str)).sum()) == 0
    assert int((compare["new_start_signal"].astype(int) != compare["risk_start_signal"].astype(int)).sum()) == 0
    assert int((compare["new_end_signal"].astype(int) != compare["risk_end_signal"].astype(int)).sum()) == 0


def test_macro5_core15_family_coverage_is_complete() -> None:
    root = Path(__file__).resolve().parents[1]
    ctx = D1C1Context(root, root.parent / "macro_dashboard_kospi")
    metadata = pd.read_parquet(ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet")

    assert metadata["indicator_id"].nunique() == 15
    assert metadata["candidate_id"].nunique() == 47
