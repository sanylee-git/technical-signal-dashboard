"""Freeze the Stage 3.1 files that Stage 4 must not mutate."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "kosdaq_macro7_assets/kosdaq_macro7_presentation_baseline.json"
FILES = [
    "kosdaq_macro7_runtime/presentation_payload.py",
    "kosdaq_macro7_assets/kosdaq_macro7_presentation_contract.json",
    "tools/kosdaq_macro7_build_presentation_contract.py",
    "tools/kosdaq_macro7_validate_presentation_payload.py",
    "tests/test_kosdaq_macro7_d2_1_presentation_payload.py",
    "reports/kosdaq_macro7_d2_1_presentation_payload.md",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    payload = {
        "contract_version": "kosdaq_macro7_d2_1_presentation_baseline_v1",
        "gate": "PASS_KOSDAQ_MACRO7_D2_1_PRESENTATION_PAYLOAD_READY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage4_immutable_files": [
            {"relative_path": relative, "sha256": _sha256(ROOT / relative)}
            for relative in FILES
        ],
        "stage4_ui_contract": {
            "default_selected_candidate": "combo2_m7_k4_l3_58c1eaea19e6d371",
            "selection_semantics": "UI_INITIAL_DISPLAY_ONLY",
            "main_assignment": False,
            "ui_side_model_calculation": False,
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
