from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_runtime import run_live_runtime
from kosdaq_macro7_runtime.live_sources import SOURCE_SPECS
from kosdaq_macro7_runtime.presentation_payload import build_presentation_payload
from tools.kosdaq_macro7_validate_presentation_payload import validate


def _frames(*, stale_vix: bool = False) -> dict[str, pd.DataFrame]:
    dates = pd.to_datetime(["2026-07-24", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"])
    frames: dict[str, pd.DataFrame] = {}
    for source_id, spec in SOURCE_SPECS.items():
        source_dates = pd.to_datetime(["2026-07-20"]) if source_id == "vix" and stale_vix else dates
        records = []
        for index, date in enumerate(source_dates):
            record = {
                "source_id": source_id, "provider": spec.provider, "provider_identifier": spec.provider_identifier,
                "observation_date": date, "publication_date": pd.NaT, "value": float(100 + index),
                "valid": True, "status": "FETCH_OK", "invalid_reason": "", "fetched_at_utc": "2026-08-03T00:00:00+00:00",
                "source_route": "fixture", "error_type": "", "error_message": "",
            }
            if source_id == "kosdaq_ohlcv":
                record.update({"open": 700.0 + index, "high": 710.0 + index, "low": 695.0 + index, "close": 705.0 + index, "volume": 1000 + index})
                record["value"] = record["close"]
            records.append(record)
        frames[source_id] = pd.DataFrame(records)
    return frames


def test_presentation_payload_is_chart_ready_and_matches_stage3_state() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), provider_frames=_frames())
    payload = build_presentation_payload(live)
    validation = validate(live_payload=live, presentation_payload=payload)
    assert validation["gate"] == "PASS_KOSDAQ_MACRO7_D2_1_PRESENTATION_PAYLOAD_READY"
    assert validation["chart_state_parity_mismatch"] == 0
    assert validation["candidate_history_after_basis_count"] == 0
    assert validation["component_history_after_basis_count"] == 0
    assert validation["benchmark_history_after_basis_count"] == 0
    assert validation["frozen_display_metric_max_abs_delta"] <= 5e-9
    assert payload["snapshot"]["candidate_id"].tolist()[5] == "combo2_m7_k4_l3_58c1eaea19e6d371"


def test_unavailable_stays_unavailable_in_presentation_payload() -> None:
    live = run_live_runtime(as_of=datetime(2026, 8, 1, 8, tzinfo=timezone.utc), provider_frames=_frames(stale_vix=True))
    payload = build_presentation_payload(live)
    unavailable = payload["snapshot"].loc[payload["snapshot"]["status"].eq("UNAVAILABLE")]
    assert not unavailable.empty
    assert unavailable["raw_risk_state"].isna().all()
    assert payload["ui_side_model_calculation_count"] == 0


def test_presentation_runtime_is_pure_and_market_isolated() -> None:
    source = (ROOT / "kosdaq_macro7_runtime/presentation_payload.py").read_text(encoding="utf-8")
    for forbidden in ["streamlit", "requests", "yfinance", "st.cache", "fetch_all_sources", "kospi_macro5_runtime", "kospi_macro5_assets", "macro_dashboard_kosdaq"]:
        assert forbidden not in source
