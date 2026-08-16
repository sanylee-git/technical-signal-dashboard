"""Create the immutable Stage 3.1 UI presentation contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "kosdaq_macro7_assets"
OUTPUT = ASSETS / "kosdaq_macro7_presentation_contract.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    final10 = json.loads((ASSETS / "kosdaq_macro7_final_manifest.json").read_text(encoding="utf-8"))
    payload = {
        "contract_version": "kosdaq_macro7_presentation_payload_v1",
        "stage": "D2_1_PRESENTATION_PAYLOAD",
        "input_contracts": {
            "final_manifest_sha256": _sha256(ASSETS / "kosdaq_macro7_final_manifest.json"),
            "live_source_contract_sha256": _sha256(ASSETS / "kosdaq_macro7_live_source_contract.json"),
            "frozen_cutoff": final10["contracts"]["frozen"]["frozen_cutoff_date"],
        },
        "default_selected_candidate": "combo2_m7_k4_l3_58c1eaea19e6d371",
        "default_selected_slot": {"model_family": "COMBO2", "display_slot": 1, "display_role": "성과 대표"},
        "selection_semantics": "UI_INITIAL_DISPLAY_ONLY",
        "main_assignment": False,
        "candidate_ranking_change": False,
        "ui_side_model_calculation": False,
        "payload_fields": [
            "snapshot", "candidate_history", "component_history", "component_chart_history",
            "benchmark_history", "performance_history", "frozen_display_metrics",
            "benchmark_display_metrics", "source_status", "merge",
        ],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
