from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.kosdaq_macro7_validate_frozen_replay import validate
from kosdaq_macro7_runtime.frozen_replay import _combine


def test_frozen_replay_matches_locked_reference() -> None:
    result = validate()
    assert result["gate"] == "PASS_KOSDAQ_MACRO7_D1_FROZEN_REPLAY_PARITY_READY"
    assert result["d0_contract_drift_count"] == 0
    assert result["frozen_asset_hash_mismatch_count"] == 0
    assert all(check["total_mismatch"] == 0 for check in result["checks"].values())
    assert result["validity_mask_parity_mismatch"] == 0
    assert result["invalid_component_as_risk_on_count"] == 0
    assert result["final_t1_application_count"] == 1
    assert result["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert result["network_call_count"] == 0
    assert result["max_metric_abs_delta"] <= 1e-12


def test_runtime_has_no_kospi_or_research_runtime_dependency() -> None:
    source = (ROOT / "kosdaq_macro7_runtime/frozen_replay.py").read_text(encoding="utf-8")
    forbidden = ["kospi_macro5_runtime", "kospi_macro5_assets", "macro_dashboard_kosdaq", "yfinance", "requests", "streamlit"]
    assert not any(token in source for token in forbidden)


def test_invalid_component_is_blocked_not_interpreted_as_risk_on() -> None:
    core = pd.DataFrame({
        "candidate_id": ["a", "b"],
        "date": [pd.Timestamp("2008-04-01"), pd.Timestamp("2008-04-01")],
        "risk_state": [False, False],
        "valid_signal": [True, False],
    })
    with pytest.raises(ValueError, match="INVALID_NOT_RISK_ON"):
        _combine(core, "blocked", ["a", "b"], 1, 0, "2008-04-01")
