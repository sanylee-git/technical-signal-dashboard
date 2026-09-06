from __future__ import annotations

from pathlib import Path

import pandas as pd

from spx_macro9_runtime.frozen_runtime import run_frozen_runtime
from spx_macro9_runtime.presentation_payload import build_presentation_payload


ROOT = Path(__file__).resolve().parents[1]


def test_spx_presentation_payload_is_final10_and_s_p_owned() -> None:
    payload = build_presentation_payload(run_frozen_runtime())
    final = payload["final10"]
    assert len(final) == 10
    assert final["model_family"].value_counts().to_dict() == {"COMBO1": 5, "COMBO2": 5}
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert payload["combo2_input_semantics"] == "CHILD_COMBO1_RAW_RISK_STATE"
    assert payload["final_t1_application_count"] == 1
    assert payload["ui_side_model_calculation_count"] == 0
    assert set(payload["snapshot"]["basis_date"]) == {"2026-08-21"}
    assert set(payload["benchmark_history"]["candidate_id"]) == set(final["candidate_id"])


def test_spx_ui_has_independent_namespace_and_route() -> None:
    ui = (ROOT / "spx_macro9_ui.py").read_text(encoding="utf-8")
    app = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    assert "from spx_macro9_runtime" in ui
    assert "def render_macro9_spx_section" in ui
    assert "macro9_spx_" in ui
    assert "nasdaq_macro8_runtime" not in ui
    assert "kosdaq_macro7_runtime" not in ui
    assert '"macro9_spx"' in app
    assert "render_macro9_spx_section" in app


def test_spx_component_payload_preserves_combo_chart_semantics() -> None:
    payload = build_presentation_payload(run_frozen_runtime())
    components = payload["component_history"]
    assert not components.empty
    assert set(components.loc[components["parent_candidate_id"].str.len() > 0, "component_kind"]) <= {
        "CORE_INDICATOR",
        "CHILD_COMBO1_RAW_STATE",
    }
    assert not payload["component_chart_history"].empty
    assert pd.to_datetime(payload["component_chart_history"]["date"]).max() == pd.Timestamp("2026-08-21")
