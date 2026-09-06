from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spx_macro9_runtime.frozen_replay import asset_sha256, raw_state_metrics, rebuild_combo1_raw, rebuild_combo2_t1, strategy_metrics, t1_from_raw


ASSETS = ROOT / "spx_macro9_assets"
FROZEN = ASSETS / "frozen"
STAGE1 = ROOT / "reports" / "spx_macro9_stage1_contract_freeze.json"


def test_spx_proxy_only_final10_frozen_replay_parity() -> None:
    contract = json.loads(STAGE1.read_text(encoding="utf-8"))
    core_raw = pd.read_parquet(FROZEN / "core15_selected_reference_raw_state.parquet")
    core_t1 = pd.read_parquet(FROZEN / "core15_selected_reference_t1_state.parquet")
    core_valid = pd.read_parquet(FROZEN / "core15_selected_reference_valid_signal.parquet")
    child_raw = pd.read_parquet(FROZEN / "combo2_required_child_raw_state.parquet")
    final_combo1_reference = pd.read_parquet(FROZEN / "final_combo1_reference_t1_state.parquet")
    final_combo2_reference = pd.read_parquet(FROZEN / "final_combo2_reference_t1_state.parquet")
    metrics_reference = pd.read_parquet(FROZEN / "final10_frozen_replay_metrics.parquet").set_index("candidate_id")
    benchmark = pd.read_parquet(FROZEN / "frozen_spx_benchmark_close.parquet")

    assert len(core_raw) == len(core_t1) == len(core_valid) == len(final_combo2_reference) == 4628
    assert len(final_combo1_reference) == 3240
    assert core_t1["date"].equals(core_valid["date"])
    for candidate_id in core_raw.columns.drop("date"):
        assert np.array_equal(
            core_t1[candidate_id].to_numpy(dtype=np.int8)[1:],
            core_raw[candidate_id].to_numpy(dtype=np.int8)[:-1],
        ), candidate_id
    final_combo1_raw: dict[str, np.ndarray] = {}
    final_combo2_raw: dict[str, np.ndarray] = {}
    for item in contract["final_combo1"]:
        candidate_id = item["candidate_id"]
        expected = final_combo1_reference[candidate_id].to_numpy(dtype=np.int8)
        raw, _active = rebuild_combo1_raw(core_raw, core_valid, item["component_ids"], item["K"], item["L"])
        actual = t1_from_raw(raw, core_raw["date"], final_combo1_reference["date"])
        assert np.array_equal(actual, expected), candidate_id
        final_combo1_raw[candidate_id] = raw

    for item in contract["final_combo2"]:
        candidate_id = item["candidate_id"]
        expected = final_combo2_reference[candidate_id].to_numpy(dtype=np.int8)
        actual, raw = rebuild_combo2_t1(child_raw, item["child_combo1_ids"], item["K"], item["L"], pd.DatetimeIndex(final_combo2_reference["date"]))
        assert np.array_equal(actual, expected), candidate_id
        final_combo2_raw[candidate_id] = raw

    for candidate_id, expected in metrics_reference.iterrows():
        reference = final_combo1_reference if expected["family"] == "Combo1" else final_combo2_reference
        values = strategy_metrics(reference[candidate_id].to_numpy(dtype=np.int8), reference["date"], benchmark)
        for field in ("cagr", "mdd", "calmar", "total_return"):
            assert abs(float(values[field]) - float(expected[field])) <= 1e-12, (candidate_id, field)
        raw = final_combo1_raw[candidate_id] if expected["family"] == "Combo1" else final_combo2_raw[candidate_id]
        raw_dates = core_raw["date"] if expected["family"] == "Combo1" else child_raw["date"]
        raw_values = raw_state_metrics(raw, raw_dates, reference["date"])
        for field in ("risk_off_ratio", "short_cycle_20d_ratio"):
            assert abs(float(raw_values[field]) - float(expected[field])) <= 1e-12, (candidate_id, field)
        assert int(raw_values["risk_off_cycle_count"]) == int(expected["risk_off_cycle_count"])
        assert int(values["transition_count"]) == int(expected["transition_count"])


def test_spx_macro9_manifest_owns_all_runtime_inputs() -> None:
    manifest_path = FROZEN / "spx_macro9_frozen_asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS_SPX_MACRO9_STAGE2_FROZEN_ASSETS_BUILT"
    assert manifest["runtime_dependency"] == "DASHBOARD_OWNED_ASSETS_ONLY"
    assert manifest["semantics"]["combo2_input"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert manifest["semantics"]["final_t1_application_count"] == 1
    assert manifest["semantics"]["proxy_only"] is True
    assert manifest["semantics"]["direct_oas_or_stitching"] == "FORBIDDEN"
    for relative_path, details in manifest["outputs"].items():
        assert asset_sha256(ASSETS / relative_path) == details["sha256"]
