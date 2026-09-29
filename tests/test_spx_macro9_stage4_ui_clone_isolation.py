from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spx_macro9_runtime.presentation_payload import build_presentation_payload
from spx_macro9_runtime.selected_final20_runtime import run_selected_final20_runtime
from spx_macro9_ui import _candidate_label, _display_final


EXPECTED_COMBO1 = [
    "9b0bf6eb468f0e0f9ead4022",
    "e4ad56aa66de8a3f2fb7c645",
    "3cb3f1e1d583f16150bb3f31",
    "39100770c8e16a06aee67170",
    "3802b3ffb79163e6e960dd94",
    "1cb2304e4f83508d7d20b788",
    "a18c14e3322e95354544ce0d",
    "5ce143a5e041d5278eeb537c",
    "c1cc6ea8f2ec0b4f5b9abc0a",
    "87613cddc0e7cdb24237e423",
]
EXPECTED_COMBO2 = [
    "c9d4c64e586e2e9f8fb2cff1",
    "e6d450aa79ca39a713ba2558",
    "56965121941b6abcf928fe96",
    "6b4595522bbed808d41be978",
    "b524905cfdecdc45c5cfc205",
    "3e58ad167be4bb0aad010eb9",
    "98ba4dad1278e9013a4a3f38",
    "1cd298482f996815f2892090",
    "146a32d0a91c4e8068ff600e",
    "03b4e0be833b4c67d0ed7cdf",
]


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    return build_presentation_payload(run_selected_final20_runtime(provider_frames={}))


def test_spx_selected_final20_payload_uses_pinned_models_and_lineage(payload: dict[str, object]) -> None:
    final = payload["final10"]
    assert len(final) == 20
    assert final["model_family"].value_counts().to_dict() == {"COMBO1": 10, "COMBO2": 10}
    assert _display_final(final).shape[0] == 20
    assert final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO1
    assert final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO2
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert payload["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert payload["final_t1_application_count"] == 1
    assert payload["ui_side_model_calculation_count"] == 0
    assert set(payload["snapshot"]["basis_date"]) == {"2026-08-21"}
    assert set(payload["benchmark_history"]["candidate_id"]) == set(final["candidate_id"])


def test_spx_selected_final20_payload_has_component_and_chart_history(payload: dict[str, object]) -> None:
    assert payload["candidate_history"]["candidate_id"].nunique() == 20
    assert payload["component_history"]["parent_candidate_id"].nunique() == 20
    assert set(payload["component_history"]["component_kind"]) <= {
        "CORE_INDICATOR",
        "CHILD_COMBO1_RAW_STATE",
    }
    chart = payload["component_chart_history"]
    assert chart["component_id"].nunique() == 69
    assert pd.to_datetime(chart["date"]).max() == pd.Timestamp("2026-08-21")


def test_spx_combo2_main1_is_the_default_and_tab_uses_operator_ui(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    combo1_main1 = final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order").iloc[0]
    combo2_main1 = final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order").iloc[0]
    assert combo1_main1["candidate_id"] == "9b0bf6eb468f0e0f9ead4022"
    assert "Main1" in _candidate_label(combo1_main1)
    assert combo2_main1["candidate_id"] == "c9d4c64e586e2e9f8fb2cff1"
    assert "Main1" in _candidate_label(combo2_main1)

    ui = (ROOT / "spx_macro9_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    assert "run_selected_final20_runtime" in ui
    assert "render_macro9_spx_section" in app
    assert "render_snp2_combo1_trial_section" not in app
