from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KOSPI_ROOT = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kospi")
sys.path.insert(0, str(ROOT))

from kospi_macro5_runtime.engine import D1C1Context, build_dependency_graph, replay_frozen_signals


def test_d1c1_dependency_graph_has_final9_lineage() -> None:
    graph = build_dependency_graph(D1C1Context(ROOT, KOSPI_ROOT))
    assert graph["dependency_missing_count"] == 0
    assert graph["final9_count"] == 9
    assert graph["required_child_combo1_count"] == 17
    assert graph["required_core15_component_count"] == 47


def test_d1c1_runtime_contract_records_raw_state_semantics() -> None:
    contract = json.loads((ROOT / "kospi_macro5_assets/kospi_d1c1_runtime_contract.json").read_text())
    semantics = contract["signal_semantics"]
    assert semantics["combo2_input"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert semantics["combo2_child_t1_forbidden"] is True
    assert semantics["final_t1_applied_once"] is True
    assert semantics["missing_as_risk_on_forbidden"] is True


def test_d1c1_frozen_replay_parity_passes() -> None:
    result = replay_frozen_signals(D1C1Context(ROOT, KOSPI_ROOT))
    assert result["gate"] == "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY"
    assert result["core15_state_mismatch_count"] == 0
    assert result["combo_final_t1_mismatch_count"] == 0


def test_d1c11_direct_runtime_hardening_manifest_passes() -> None:
    manifest = json.loads((ROOT / "reports/kospi_macro5_d1c11_manifest.json").read_text())
    assert manifest["c1a1_gate"] == "PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED"
    assert manifest["core15_state_event_mismatch"] == 0
    assert manifest["core15_validity_mismatch"] == 0
    assert manifest["child_raw_state_mismatch"] == 0
    assert manifest["final_raw_state_mismatch"] == 0
    assert manifest["final_t1_mismatch"] == 0
    assert manifest["combo2_child_t1_applied_count"] == 0
    assert manifest["final_t1_application_count"] == 1
