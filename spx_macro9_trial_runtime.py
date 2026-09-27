"""Read-only loader for the three-model S&P2 visual validation preview."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "spx_macro9_assets" / "trial_combo1_3"
EXPECTED_IDS = (
    "3e12d084c6d477f9341a659b",
    "1cb2304e4f83508d7d20b788",
    "9b0bf6eb468f0e0f9ead4022",
)
EXPECTED_OUTPUTS = (
    "candidate_history.parquet",
    "component_history.parquet",
    "component_chart_history.parquet",
    "benchmark_history.parquet",
    "candidate_metrics.parquet",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@st.cache_data(show_spinner=False)
def load_trial_payload() -> dict[str, Any]:
    """Load only pinned, locally materialized Frozen preview assets."""
    manifest_path = ASSET_DIR / "trial_asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_SNP2_COMBO1_TRIAL_FROZEN_ASSETS_READY":
        raise RuntimeError("S&P2 trial asset gate is not PASS")
    if manifest.get("mode") != "FROZEN_VISUAL_VALIDATION_ONLY":
        raise RuntimeError("S&P2 trial must remain Frozen-only")
    if tuple(manifest.get("candidates", ())) != EXPECTED_IDS or manifest.get("combo2_count") != 0:
        raise RuntimeError("S&P2 preview candidate contract mismatch")
    if manifest.get("evaluation_period") != ["2008-04-01", "2026-08-21"] or manifest.get("evaluation_sessions") != 4628:
        raise RuntimeError("S&P2 Frozen evaluation window mismatch")
    qa = manifest.get("qa", {})
    required_zero = (
        "component_raw_valid_mismatch",
        "component_transition_mismatch",
        "candidate_official_t1_mismatch",
        "candidate_invalid_state_cells",
        "additional_t1_application_count",
        "network_fetch",
        "combo2_count",
    )
    if any(int(qa.get(key, -1)) != 0 for key in required_zero):
        raise RuntimeError(f"S&P2 preview QA gate failed: {qa}")
    if qa.get("official_t1_application_count") != 1:
        raise RuntimeError("S&P2 official T+1 must be applied exactly once")

    frames: dict[str, pd.DataFrame] = {}
    for name in EXPECTED_OUTPUTS:
        path = ASSET_DIR / name
        pin = manifest.get("outputs", {}).get(name, {})
        if not path.is_file() or _sha256(path) != pin.get("sha256"):
            raise RuntimeError(f"S&P2 preview asset SHA mismatch: {name}")
        frame = pd.read_parquet(path)
        if len(frame) != int(pin.get("rows", -1)):
            raise RuntimeError(f"S&P2 preview asset row-count mismatch: {name}")
        if "date" in frame:
            frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
        frames[name] = frame

    metrics = frames["candidate_metrics.parquet"]
    if tuple(metrics.candidate_id.astype(str)) != EXPECTED_IDS:
        raise RuntimeError("S&P2 preview candidate ordering mismatch")
    if not metrics.model_family.eq("COMBO1").all() or len(metrics) != 3:
        raise RuntimeError("S&P2 preview must contain exactly three Combo1 candidates")
    history = frames["candidate_history.parquet"]
    membership = frames["component_history.parquet"]
    for candidate_id in EXPECTED_IDS:
        model = history.loc[history.candidate_id.astype(str).eq(candidate_id)].sort_values("date").reset_index(drop=True)
        expected_n = int(metrics.loc[metrics.candidate_id.eq(candidate_id), "n"].iloc[0])
        component_ids = membership.loc[membership.parent_candidate_id.eq(candidate_id), "component_id"].drop_duplicates()
        if len(component_ids) != expected_n:
            raise RuntimeError(f"S&P2 candidate component lineage count mismatch: {candidate_id}")
        if len(model) != 4628 or model.date.duplicated().any() or not model.date.is_monotonic_increasing:
            raise RuntimeError(f"S&P2 candidate history calendar mismatch: {candidate_id}")
        state = model.strategy_risk_state.astype(int)
        if not state.isin([0, 1]).all():
            raise RuntimeError(f"S&P2 candidate has invalid state: {candidate_id}")
        previous = state.shift(1, fill_value=int(state.iloc[0]))
        if not (model.risk_start.astype(bool).to_numpy() == (state.eq(1) & previous.eq(0)).to_numpy()).all():
            raise RuntimeError(f"S&P2 candidate START markers disagree with official T+1 state: {candidate_id}")
        if not (model.risk_end.astype(bool).to_numpy() == (state.eq(0) & previous.eq(1)).to_numpy()).all():
            raise RuntimeError(f"S&P2 candidate END markers disagree with official T+1 state: {candidate_id}")

    latest_active = history.sort_values("date").groupby("candidate_id", sort=False).tail(1).set_index("candidate_id").active_count
    metrics["active_count"] = metrics.candidate_id.map(latest_active).astype(int)

    return {
        "manifest": manifest,
        "candidate_metrics": metrics,
        "candidate_history": frames["candidate_history.parquet"],
        "component_history": frames["component_history.parquet"],
        "component_chart_history": frames["component_chart_history.parquet"],
        "benchmark_history": frames["benchmark_history.parquet"],
        "ui_side_model_calculation_count": 0,
    }
