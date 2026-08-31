"""Frozen-only NASDAQ Macro8 runtime.

The Core15 operating contract deliberately prohibits provider calls. This
runtime therefore loads and verifies dashboard-owned Frozen assets only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .frozen_replay import asset_sha256, replay_core, replay_final20, replay_final20_history


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "nasdaq_macro8_assets"
FROZEN = ASSETS / "frozen"


def _date(value: object) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _load_verified_assets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = json.loads((FROZEN / "nasdaq_macro8_frozen_asset_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("gate") != "PASS_NASDAQ_MACRO8_D1_FROZEN_REPLAY_PARITY_READY":
        raise RuntimeError("NASDAQ Macro8 Frozen asset manifest is not PASS")
    for item in manifest["assets"].values():
        records = item.values() if isinstance(item, dict) and "path" not in item else (item,)
        for record in records:
            path = ROOT / record["path"]
            if asset_sha256(path) != record["sha256"]:
                raise RuntimeError(f"NASDAQ Macro8 Frozen asset SHA mismatch: {path.name}")
    panel = pd.read_parquet(FROZEN / "frozen_nasdaq_core15_input.parquet")
    registry = pd.read_parquet(FROZEN / "core15_selected_candidate_registry.parquet")
    final20 = pd.read_csv(ASSETS / "nasdaq_macro8_final20.csv")
    children = pd.read_csv(ASSETS / "nasdaq_macro8_combo2_child_mapping.csv")
    return panel, registry, final20, children, manifest


def _snapshot(final20: pd.DataFrame, history: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    close = panel[["date", "ndx_close"]].copy()
    close["date"] = pd.to_datetime(close["date"]).dt.normalize()
    rows: list[dict[str, object]] = []
    for candidate in final20.sort_values("display_order", kind="mergesort").itertuples(index=False):
        states = history.loc[history["candidate_id"].eq(candidate.candidate_id)].sort_values("date", kind="mergesort").reset_index(drop=True)
        if states.empty or not states["valid"].all():
            raise RuntimeError(f"Frozen Final20 candidate history unavailable: {candidate.candidate_id}")
        current = states.iloc[-1]
        previous_state = states.loc[states["strategy_risk_state"].ne(current.strategy_risk_state)]
        start_index = int(previous_state.index[-1] + 1) if not previous_state.empty else 0
        state_start = pd.Timestamp(states.iloc[start_index]["date"])
        segment = close.loc[close["date"].between(state_start, current.date), "ndx_close"].dropna()
        segment_return = None if len(segment) < 2 else float(segment.iloc[-1] / segment.iloc[0] - 1.0)
        week_ago = states.iloc[-6] if len(states) >= 6 else None
        rows.append({
            "candidate_id": str(candidate.candidate_id),
            "family": str(candidate.family),
            "selection_type": str(candidate.selection_type),
            "basis_date": _date(current.date),
            "calculable": True,
            "availability_status": "FROZEN_ONLY",
            "strategy_risk_state": int(current.strategy_risk_state),
            "active_count": int(current.active_count),
            "K": int(candidate.K),
            "L": int(candidate.L),
            "current_state_start_date": _date(state_start),
            "current_duration_trading_days": int(len(states) - start_index),
            "current_segment_return": segment_return,
            "current_segment_return_end_date": _date(current.date),
            "week_ago_basis_date": None if week_ago is None else _date(week_ago.date),
            "week_ago_strategy_risk_state": None if week_ago is None else int(week_ago.strategy_risk_state),
            "week_ago_active_count": None if week_ago is None else int(week_ago.active_count),
            "today_transition": "RISK_OFF_START" if bool(current.risk_start) else "RISK_OFF_END" if bool(current.risk_end) else "NONE",
        })
    return pd.DataFrame(rows)


def run_frozen_runtime() -> dict[str, Any]:
    """Produce Final20 state snapshots without network, cache, or session state."""
    panel, registry, final20, children, manifest = _load_verified_assets()
    core = replay_core(panel, registry)
    metrics = replay_final20(panel, final20, children, core)
    history = replay_final20_history(panel, final20, children, core)
    snapshot = _snapshot(final20, history, panel)
    cutoff = pd.Timestamp(pd.to_datetime(panel["date"]).max()).normalize()
    if snapshot["basis_date"].nunique() != 1 or snapshot["basis_date"].iloc[0] != cutoff.strftime("%Y-%m-%d"):
        raise RuntimeError("Frozen Final20 basis date contract failed")
    return {
        "runtime_mode": "FROZEN_ONLY",
        "network_access": False,
        "basis_date": cutoff.strftime("%Y-%m-%d"),
        "proxy_only": True,
        "direct_oas_used": False,
        "asset_manifest_sha256": asset_sha256(FROZEN / "nasdaq_macro8_frozen_asset_manifest.json"),
        "snapshot": snapshot,
        "metrics": metrics,
        "history": history,
        # Presentation modules consume these verified Frozen inputs only.
        "panel": panel,
        "registry": registry,
        "final20": final20,
        "children": children,
        "core": core,
    }
