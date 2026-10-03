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
    "da862ec08d016b6f056c71d4",
    "e4ad56aa66de8a3f2fb7c645",
    "d347f67c803b8c70ccf93c53",
    "3b836baf07044098ee443d40",
    "cc58a67d98a9db7b6228a5b6",
]
EXPECTED_COMBO2 = [
    "6b4595522bbed808d41be978",
    "c9d4c64e586e2e9f8fb2cff1",
    "146a32d0a91c4e8068ff600e",
    "56965121941b6abcf928fe96",
    "b524905cfdecdc45c5cfc205",
]


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    return build_presentation_payload(run_selected_final20_runtime(provider_frames={}))


def test_spx_selected_final10_payload_uses_pinned_models_and_lineage(payload: dict[str, object]) -> None:
    final = payload["final10"]
    assert len(final) == 10
    assert final["model_family"].value_counts().to_dict() == {"COMBO1": 5, "COMBO2": 5}
    assert _display_final(final).shape[0] == 10
    assert final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO1
    assert final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")["candidate_id"].tolist() == EXPECTED_COMBO2
    assert final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")["display_role"].tolist() == [
        "Main1 · 효율적 밸런스형",
        "Main2 · 고성과·저오경보형",
        "고성과·빠른복귀형",
        "조기경보·빠른복귀형",
        "위기경보·저오경보형",
    ]
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert payload["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert payload["final_t1_application_count"] == 1
    assert payload["ui_side_model_calculation_count"] == 0
    assert set(payload["snapshot"]["basis_date"]) == {"2026-08-21"}
    assert set(payload["benchmark_history"]["candidate_id"]) == set(final["candidate_id"])


def test_spx_selected_final10_payload_has_component_and_chart_history(payload: dict[str, object]) -> None:
    assert payload["candidate_history"]["candidate_id"].nunique() == 10
    assert payload["component_history"]["parent_candidate_id"].nunique() == 10
    assert set(payload["component_history"]["component_kind"]) <= {
        "CORE_INDICATOR",
        "CHILD_COMBO1_RAW_STATE",
    }
    chart = payload["component_chart_history"]
    assert chart["component_id"].nunique() == 69
    assert pd.to_datetime(chart["date"]).max() == pd.Timestamp("2026-08-21")


def test_spx_combo2_main1_is_the_default_and_tab_uses_operator_ui(payload: dict[str, object]) -> None:
    final = _display_final(payload["final10"])
    combo1 = final.loc[final["model_family"].eq("COMBO1")].sort_values("display_order")
    combo2 = final.loc[final["model_family"].eq("COMBO2")].sort_values("display_order")
    combo1_main1, combo1_main2 = combo1.iloc[0], combo1.iloc[1]
    combo2_main1, combo2_main2 = combo2.iloc[0], combo2.iloc[1]
    assert combo1_main1["candidate_id"] == "da862ec08d016b6f056c71d4"
    assert "Main1" in _candidate_label(combo1_main1)
    assert combo1_main1["display_role"] == "Main1 · 효율적 밸런스형"
    assert combo1_main2["candidate_id"] == "e4ad56aa66de8a3f2fb7c645"
    assert "Main2" in _candidate_label(combo1_main2)
    assert combo1_main2["display_role"] == "Main2 · 고성과·저오경보형"
    assert combo2_main1["candidate_id"] == "6b4595522bbed808d41be978"
    assert "Main1" in _candidate_label(combo2_main1)
    assert combo2_main2["candidate_id"] == "c9d4c64e586e2e9f8fb2cff1"
    assert "Main2" in _candidate_label(combo2_main2)
    assert combo2.iloc[0]["candidate_id"] == "6b4595522bbed808d41be978"

    ui = (ROOT / "spx_macro9_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    assert "run_selected_final20_runtime" in ui
    assert "macro9_spx_preset_5x5" in ui
    assert "render_macro9_spx_section" in app
    assert "render_snp2_combo1_trial_section" not in app
