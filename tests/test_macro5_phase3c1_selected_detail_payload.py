from __future__ import annotations

from pathlib import Path

import pandas as pd

from kospi_macro5_runtime import page_adapter as pa
from kospi_macro5_runtime.engine import D1C1Context


ROOT = Path(__file__).resolve().parents[1]
CTX = D1C1Context(ROOT, ROOT.parent / "macro_dashboard_kospi")


def _tail_live_for(candidate_id: str) -> dict[str, pd.DataFrame]:
    final9 = pa.read_json(CTX.asset_dir / "kospi_final9_component_dictionary.json")
    spec = final9[candidate_id]
    frozen = pa._read_component_reference_frame(CTX, {candidate_id})
    tail_date = pd.to_datetime(frozen["date"]).max() + pd.offsets.BDay(1)
    common = {
        "date": tail_date,
        "risk_state": 1,
        "raw_risk_state": 1,
        "risk_start_signal": False,
        "risk_end_signal": False,
        "valid_signal": True,
        "calculation_status": "CALCULABLE",
        "calculation_reason": "",
        "active_count": 1,
        "component_count": len(spec.get("component_ids", [])),
    }
    if spec["model_type"] == "combo1":
        core = pd.DataFrame([{**common, "component_id": component_id} for component_id in spec["component_ids"]])
        child = pd.DataFrame()
    else:
        core = pd.DataFrame()
        child = pd.DataFrame([{**common, "combo1_id": component_id} for component_id in spec["component_ids"]])
    return {"core15": core, "child_combo1": child}


def test_selected_component_history_matches_full_slice_for_combo1_and_combo2() -> None:
    final9 = pa.read_json(CTX.asset_dir / "kospi_final9_component_dictionary.json")
    candidate_ids = [
        next(candidate_id for candidate_id, spec in final9.items() if spec["model_type"] == "combo1"),
        next(candidate_id for candidate_id, spec in final9.items() if spec["model_type"] == "combo2"),
    ]

    for candidate_id in candidate_ids:
        live = _tail_live_for(candidate_id)
        full_slice = pa._component_signal_history(CTX, live).loc[
            lambda frame: frame["parent_candidate_id"].eq(candidate_id)
        ].reset_index(drop=True)
        selected = pa._component_signal_history(CTX, live, candidate_ids=[candidate_id]).reset_index(drop=True)
        pd.testing.assert_frame_equal(selected, full_slice)


def test_selected_component_history_helper_does_not_fetch_or_recompute(monkeypatch) -> None:
    final9 = pa.read_json(CTX.asset_dir / "kospi_final9_component_dictionary.json")
    candidate_id = next(candidate_id for candidate_id, spec in final9.items() if spec["model_type"] == "combo1")
    live = _tail_live_for(candidate_id)

    def fail_unexpected_call(*_args, **_kwargs):
        raise AssertionError("selected detail helper must not fetch sources or recompute the live tree")

    monkeypatch.setattr(pa, "fetch_source", fail_unexpected_call)
    monkeypatch.setattr(pa, "compute_live_tree", fail_unexpected_call)
    payload = {
        "core15_component_history": live["core15"],
        "child_combo1_history": live["child_combo1"],
    }

    selected = pa.build_selected_component_signal_history(payload, candidate_id)

    assert not selected.empty
    assert set(selected["parent_candidate_id"].astype(str)) == {candidate_id}
