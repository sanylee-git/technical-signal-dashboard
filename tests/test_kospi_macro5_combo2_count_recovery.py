from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from kospi_macro5_runtime.engine import hysteresis_from_counts, t1_position_from_raw
from kospi_macro5_runtime.page_adapter import _recover_combo2_frozen_counts


ROOT = Path(__file__).resolve().parents[1]


def test_combo2_counts_recover_only_from_complete_exact_component_sets() -> None:
    candidate_id = "m2::candidate"
    frozen = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "candidate_id": [candidate_id, candidate_id],
            "model_type": ["combo2", "combo2"],
            "on_count": [pd.NA, pd.NA],
        }
    )
    components = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-02", "2026-01-05"]),
            "parent_candidate_id": [candidate_id] * 3,
            "component_id": ["child-a", "child-b", "child-a"],
            "component_risk_state": [1, 0, 1],
            "valid_signal": [True, True, True],
        }
    )
    specs = pd.DataFrame(
        {
            "candidate_id": [candidate_id],
            "model_type": ["combo2"],
            "component_ids_json": [json.dumps(["child-a", "child-b"])],
        }
    )

    recovered, qa = _recover_combo2_frozen_counts(frozen, components, specs)

    assert recovered["on_count"].iloc[0] == 1
    assert pd.isna(recovered["on_count"].iloc[1])
    assert qa.loc[0, "recovered_count_rows"] == 1
    assert qa.loc[0, "remaining_count_missing"] == 1
    assert qa.loc[0, "status"] == "PARTIAL_OR_MISMATCH"


def test_official_kospi_combo2_frozen_counts_match_saved_raw_and_t1_states() -> None:
    assets = ROOT / "kospi_macro5_assets"
    operating = json.loads((assets / "kospi_final5_operating_dictionary.json").read_text())
    combo2 = [row for row in operating["candidates"] if row["model_type"] == "combo2"]
    specs = pd.DataFrame(
        [
            {
                "candidate_id": row["candidate_id"],
                "model_type": row["model_type"],
                "component_ids_json": json.dumps(row["component_ids"]),
            }
            for row in combo2
        ]
    )
    frozen = pd.read_parquet(assets / "kospi_final9_reference_signals.parquet")
    components = pd.read_parquet(assets / "kospi_final9_component_reference_signals.parquet")

    recovered, qa = _recover_combo2_frozen_counts(frozen, components, specs)

    assert len(combo2) == 5
    assert qa["status"].eq("PASS").all()
    assert qa["remaining_count_missing"].eq(0).all()
    assert qa["existing_count_mismatch"].eq(0).all()

    for candidate in combo2:
        candidate_id = candidate["candidate_id"]
        source = recovered.loc[
            recovered["candidate_id"].astype(str).eq(candidate_id)
        ].sort_values("date")
        count = pd.to_numeric(source["on_count"], errors="raise").astype(int)
        raw = hysteresis_from_counts(count, int(candidate["K"]), int(candidate["L"]))
        expected_raw = pd.to_numeric(source["raw_risk_state"], errors="raise").astype(int).reset_index(drop=True)
        expected_t1 = pd.to_numeric(source["t1_position"], errors="raise").astype(int).reset_index(drop=True)

        assert count.notna().all()
        assert np.array_equal(raw.to_numpy(), expected_raw.to_numpy())
        assert np.array_equal(t1_position_from_raw(raw).to_numpy(), expected_t1.to_numpy())
