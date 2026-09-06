"""Frozen-only state payload for the S&P Macro9 Proxy-only contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import asset_sha256, rebuild_combo1_raw, rebuild_combo2_t1
from .live_replay import replay_core


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "spx_macro9_assets"
FROZEN = ASSETS / "frozen"


def _date(value: object) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = json.loads((FROZEN / "spx_macro9_live_asset_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_SPX_MACRO9_STAGE3_LIVE_INPUT_ASSETS_READY":
        raise RuntimeError("S&P Macro9 live-input assets are not verified")
    for relative, record in manifest["outputs"].items():
        if asset_sha256(ASSETS / relative) != record["sha256"]:
            raise RuntimeError(f"S&P Macro9 asset SHA mismatch: {relative}")
    panel = pd.read_parquet(FROZEN / "frozen_spx_proxy_only_core15_input.parquet")
    registry = pd.read_parquet(FROZEN / "core15_selected_candidate_registry.parquet")
    final10 = pd.read_csv(ASSETS / "spx_macro9_final10_runtime.csv")
    children = pd.read_csv(ASSETS / "spx_macro9_combo2_child_mapping.csv")
    return panel, registry, final10, children, manifest


def _history_and_seeds(final10: pd.DataFrame, children: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    core_raw = pd.read_parquet(FROZEN / "core15_selected_reference_raw_state.parquet")
    core_valid = pd.read_parquet(FROZEN / "core15_selected_reference_valid_signal.parquet")
    child_raw = pd.read_parquet(FROZEN / "combo2_required_child_raw_state.parquet")
    c1_ref = pd.read_parquet(FROZEN / "final_combo1_reference_t1_state.parquet")
    c2_ref = pd.read_parquet(FROZEN / "final_combo2_reference_t1_state.parquet")
    for frame in (core_raw, core_valid, child_raw, c1_ref, c2_ref):
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()

    rows: list[pd.DataFrame] = []
    c1_raw_seed: dict[str, int] = {}
    c1_active_seed: dict[str, int] = {}
    for record in final10.loc[final10["family"].eq("Combo1")].itertuples(index=False):
        raw, active = rebuild_combo1_raw(core_raw, core_valid, str(record.component_ids_key).split("|"), int(record.K), int(record.L))
        states = c1_ref[["date", str(record.candidate_id)]].rename(columns={str(record.candidate_id): "strategy_risk_state"}).copy()
        active_by_date = pd.Series(np.r_[-1, active[:-1]], index=pd.DatetimeIndex(core_raw["date"]))
        states["active_count"] = active_by_date.reindex(pd.DatetimeIndex(states["date"])).to_numpy()
        states["candidate_id"] = str(record.candidate_id)
        rows.append(states)
        c1_raw_seed[str(record.candidate_id)] = int(raw[-1])
        c1_active_seed[str(record.candidate_id)] = int(active[-1])

    c2_raw_seed: dict[str, int] = {}
    c2_active_seed: dict[str, int] = {}
    child_seed: dict[str, int] = {column: int(child_raw[column].iloc[-1]) for column in child_raw.columns.drop("date")}
    for record in final10.loc[final10["family"].eq("Combo2")].itertuples(index=False):
        child = children.loc[children["parent_candidate_id"].eq(record.candidate_id)].sort_values("child_order", kind="mergesort")
        child_ids = child["child_canonical_parent_id"].astype(str).tolist()
        t1, raw = rebuild_combo2_t1(child_raw, child_ids, int(record.K), int(record.L), pd.DatetimeIndex(c2_ref["date"]))
        active_raw = np.vstack([child_raw[item].to_numpy(dtype=np.int8) for item in child_ids]).sum(axis=0, dtype=np.int16)
        positions = np.flatnonzero(pd.DatetimeIndex(child_raw["date"]).isin(pd.DatetimeIndex(c2_ref["date"])))
        states = c2_ref[["date", str(record.candidate_id)]].rename(columns={str(record.candidate_id): "strategy_risk_state"}).copy()
        states["active_count"] = active_raw[positions - 1]
        states["candidate_id"] = str(record.candidate_id)
        if not np.array_equal(t1, states["strategy_risk_state"].to_numpy(dtype=np.int8)):
            raise RuntimeError(f"Frozen Combo2 T+1 parity failed: {record.candidate_id}")
        rows.append(states)
        c2_raw_seed[str(record.candidate_id)] = int(raw[-1])
        c2_active_seed[str(record.candidate_id)] = int(active_raw[-1])

    history = pd.concat(rows, ignore_index=True)
    history["previous_strategy_risk_state"] = history.groupby("candidate_id", sort=False)["strategy_risk_state"].shift(1).fillna(0).astype("int8")
    history["risk_start"] = history["strategy_risk_state"].eq(1) & history["previous_strategy_risk_state"].eq(0)
    history["risk_end"] = history["strategy_risk_state"].eq(0) & history["previous_strategy_risk_state"].eq(1)
    history["valid"] = True
    history = history.sort_values(["candidate_id", "date"], kind="mergesort").reset_index(drop=True)
    return history, {"c1_raw": c1_raw_seed, "c1_active": c1_active_seed, "c2_raw": c2_raw_seed, "c2_active": c2_active_seed, "child_raw": child_seed}


def _snapshot(final10: pd.DataFrame, history: pd.DataFrame, panel: pd.DataFrame, *, status: str) -> pd.DataFrame:
    close = panel[["date", "close"]].copy()
    close["date"] = pd.to_datetime(close["date"]).dt.normalize()
    rows: list[dict[str, object]] = []
    for candidate in final10.sort_values(["family", "display_order"], kind="mergesort").itertuples(index=False):
        states = history.loc[history["candidate_id"].eq(candidate.candidate_id)].sort_values("date", kind="mergesort").reset_index(drop=True)
        current = states.iloc[-1]
        prior = states.loc[states["strategy_risk_state"].ne(current.strategy_risk_state)]
        start_index = int(prior.index[-1] + 1) if not prior.empty else 0
        start = pd.Timestamp(states.iloc[start_index]["date"])
        segment = close.loc[close["date"].between(start, current.date), "close"].dropna()
        week_ago = states.iloc[-6] if len(states) >= 6 else None
        rows.append({
            "candidate_id": str(candidate.candidate_id), "family": str(candidate.family), "selection_type": str(candidate.selection_type),
            "basis_date": _date(current.date), "calculable": True, "availability_status": status,
            "strategy_risk_state": int(current.strategy_risk_state), "active_count": int(current.active_count), "K": int(candidate.K), "L": int(candidate.L),
            "current_state_start_date": _date(start), "current_duration_trading_days": int(len(states) - start_index),
            "current_segment_return": None if len(segment) < 2 else float(segment.iloc[-1] / segment.iloc[0] - 1.0),
            "current_segment_return_end_date": _date(current.date),
            "week_ago_basis_date": None if week_ago is None else _date(week_ago.date),
            "week_ago_strategy_risk_state": None if week_ago is None else int(week_ago.strategy_risk_state),
            "week_ago_active_count": None if week_ago is None else int(week_ago.active_count),
            "today_transition": "RISK_OFF_START" if bool(current.risk_start) else "RISK_OFF_END" if bool(current.risk_end) else "NONE",
        })
    return pd.DataFrame(rows)


def run_frozen_runtime() -> dict[str, Any]:
    panel, registry, final10, children, manifest = _load()
    history, seeds = _history_and_seeds(final10, children)
    cutoff = pd.Timestamp(panel["date"].max()).normalize()
    snapshot = _snapshot(final10, history, panel, status="FROZEN_ONLY")
    metrics = pd.read_parquet(FROZEN / "final10_frozen_replay_metrics.parquet")
    core = replay_core(panel, registry)
    return {
        "runtime_mode": "FROZEN_ONLY", "network_access": False, "basis_date": _date(cutoff), "frozen_cutoff": _date(cutoff),
        "proxy_only": True, "direct_oas_used": False, "asset_manifest_sha256": asset_sha256(FROZEN / "spx_macro9_live_asset_manifest.json"),
        "snapshot": snapshot, "metrics": metrics, "history": history, "panel": panel, "registry": registry, "final10": final10,
        "children": children, "seeds": seeds, "core": core,
    }
