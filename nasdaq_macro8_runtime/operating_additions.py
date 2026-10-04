"""Pinned NASDAQ monitoring candidates kept separate from the Frozen Final20."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import EVALUATION_END, EVALUATION_START, replay_core, replay_final20, replay_final20_history


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "nasdaq_macro8_assets"
ADDITIONS_PATH = ASSETS / "nasdaq_macro8_operating_additions.json"
MANIFEST_PATH = ASSETS / "nasdaq_macro8_operating_additions_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_operating_additions() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("gate") != "PASS_NASDAQ_OPERATING_ADDITIONS_FROZEN_PARITY":
        raise RuntimeError("NASDAQ operating additions manifest is not PASS")
    record = manifest.get("asset", {})
    if record.get("path") != ADDITIONS_PATH.relative_to(ROOT).as_posix():
        raise RuntimeError("NASDAQ operating additions asset path contract failed")
    if _sha256(ADDITIONS_PATH) != record.get("sha256"):
        raise RuntimeError("NASDAQ operating additions asset SHA mismatch")
    data = json.loads(ADDITIONS_PATH.read_text(encoding="utf-8"))
    if data.get("contract") != "nasdaq_operating_additions_v1":
        raise RuntimeError("NASDAQ operating additions contract failed")
    candidates = pd.DataFrame(data.get("candidates", []))
    counts = candidates.groupby("family")["candidate_id"].nunique().to_dict()
    if len(candidates) != 10 or counts != {"Combo1": 5, "Combo2": 5}:
        raise RuntimeError("NASDAQ operating additions must contain five unique models per combo")
    if candidates["candidate_id"].duplicated().any():
        raise RuntimeError("NASDAQ operating additions candidate IDs are not unique")
    return data


def replay_operating_additions(
    panel: pd.DataFrame,
    registry: pd.DataFrame,
    core: dict[str, dict[str, np.ndarray]],
    *,
    evaluation_end: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Replay the ten monitoring candidates with the production NASDAQ formulas."""
    data = load_operating_additions()
    definitions = pd.DataFrame(data.get("component_definitions", []))
    if definitions.empty or definitions["candidate_id"].duplicated().any():
        raise RuntimeError("NASDAQ operating additions component definitions are invalid")
    existing_ids = set(registry["candidate_id"].astype(str))
    if existing_ids.intersection(definitions["candidate_id"].astype(str)):
        raise RuntimeError("NASDAQ operating additions unexpectedly redefine a Frozen component")
    component_ids = {
        component_id
        for row in data["candidates"]
        if row["family"] == "Combo1"
        for component_id in str(row.get("component_ids_key", "")).split("|")
        if component_id
    }
    component_ids.update(
        component_id
        for row in data.get("children", [])
        for component_id in str(row.get("child_component_ids_key", "")).split("|")
        if component_id
    )
    missing_components = component_ids - existing_ids
    if missing_components != set(definitions["candidate_id"].astype(str)):
        raise RuntimeError("NASDAQ operating additions component lineage is incomplete")

    additional_core = replay_core(panel, definitions)
    combined_core = {**core, **additional_core}
    final = pd.DataFrame(data["candidates"])
    children = pd.DataFrame(data["children"])
    metrics = replay_final20(panel, final, children, combined_core, evaluation_end=evaluation_end)
    history = replay_final20_history(panel, final, children, combined_core, evaluation_end=evaluation_end)

    dates = pd.to_datetime(history["date"]).dt.normalize()
    frozen_window = history.loc[dates.between(EVALUATION_START, EVALUATION_END)]
    expected_dates = pd.DatetimeIndex(
        pd.to_datetime(panel.loc[
            panel["performance_calendar_eligible"].astype(bool)
            & pd.to_datetime(panel["date"]).dt.normalize().between(EVALUATION_START, EVALUATION_END),
            "date",
        ]).dt.normalize()
    )
    expected_hashes = {str(row["candidate_id"]): str(row["expected_state_hash"]) for row in data["candidates"]}
    for candidate_id, expected in expected_hashes.items():
        candidate = frozen_window.loc[frozen_window["candidate_id"].astype(str).eq(candidate_id)].sort_values("date")
        if not pd.DatetimeIndex(candidate["date"]).equals(expected_dates):
            raise RuntimeError(f"NASDAQ additions frozen history coverage mismatch: {candidate_id}")
        states = candidate["strategy_risk_state"].to_numpy(dtype=np.uint8)
        actual = hashlib.sha256(np.packbits(states).tobytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"NASDAQ additions frozen state hash mismatch: {candidate_id}")

    return {
        "final": final,
        "children": children,
        "registry": definitions,
        "core": additional_core,
        "metrics": metrics,
        "history": history,
        "source_run": data["source_run"],
    }
