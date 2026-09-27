"""Frozen-only state payload for the S&P Macro9 Proxy-only contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import asset_sha256
from .live_replay import performance_calendar, replay_combo1_raw_history, replay_core, replay_final10, replay_final10_history


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "spx_macro9_assets"
FROZEN = ASSETS / "frozen"
OPERATIONAL = ASSETS / "operational"
OPERATIONAL_MANIFEST = ASSETS / "snp2_operational_asset_manifest.json"


def _date(value: object) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, pd.DataFrame]:
    manifest = json.loads(OPERATIONAL_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_SPX2_OPERATIONAL_FINAL10_ASSETS_READY":
        raise RuntimeError("S&P2 operational assets are not verified")
    for relative, record in manifest["outputs"].items():
        if asset_sha256(ASSETS / relative) != record["sha256"]:
            raise RuntimeError(f"S&P2 operational asset SHA mismatch: {relative}")
    panel = pd.read_parquet(ASSETS / "operational/snp2_source_panel.parquet")
    registry = pd.read_parquet(ASSETS / "operational/snp2_single69_registry.parquet")
    final10 = pd.read_csv(ASSETS / "operational/snp2_final10.csv")
    children = pd.read_csv(ASSETS / "operational/snp2_combo2_child_mapping.csv")
    raw_seed = pd.read_parquet(ASSETS / "operational/snp2_single69_raw_seed.parquet")
    combo2_reference = pd.read_parquet(ASSETS / "operational/snp2_combo2_authoritative_t1.parquet")
    return panel, registry, final10, children, manifest, raw_seed, combo2_reference


def _authoritative_final_states(reference: pd.DataFrame, dates: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    source = reference.copy()
    source["date"] = pd.to_datetime(source["date"]).dt.normalize()
    source = source.set_index("date").reindex(dates)
    if source.isna().any().any():
        raise RuntimeError("S&P2 authoritative Combo2 T+1 date alignment failed")
    return {str(column): source[column].to_numpy(dtype=np.int8) for column in source.columns}


def _overlay_authoritative_raw(panel: pd.DataFrame, core: dict[str, dict[str, np.ndarray]], raw_seed: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    dates = pd.DatetimeIndex(pd.to_datetime(panel["date"]).dt.normalize())
    seed = raw_seed.copy()
    seed["date"] = pd.to_datetime(seed["date"]).dt.normalize()
    positions = dates.get_indexer(pd.DatetimeIndex(seed["date"]))
    if (positions < 0).any():
        raise RuntimeError("S&P2 authoritative raw seed is outside source panel")
    for candidate_id in seed.columns.drop("date"):
        if candidate_id not in core:
            raise RuntimeError(f"S&P2 authoritative raw seed candidate is not registered: {candidate_id}")
        values = pd.to_numeric(seed[candidate_id], errors="coerce").to_numpy(dtype="int8")
        core[candidate_id]["raw"][positions] = values
        core[candidate_id]["valid"][positions] = True
        core[candidate_id]["start"] = np.zeros(len(dates), dtype=bool)
        core[candidate_id]["end"] = np.zeros(len(dates), dtype=bool)
        previous = np.r_[-1, core[candidate_id]["raw"][:-1]]
        current = core[candidate_id]["raw"]
        core[candidate_id]["start"] = (current == 1) & (previous == 0)
        core[candidate_id]["end"] = (current == 0) & (previous == 1)
    return core


def _history_and_seeds(panel: pd.DataFrame, final10: pd.DataFrame, children: pd.DataFrame, core: dict[str, dict[str, np.ndarray]], authoritative_t1: dict[str, np.ndarray]) -> tuple[pd.DataFrame, dict[str, Any]]:
    history = replay_final10_history(panel, final10, children, core, authoritative_t1=authoritative_t1)
    child_history = replay_combo1_raw_history(panel, children, core, evaluation_end=pd.Timestamp(panel["date"].max()))
    latest = history.sort_values("date", kind="mergesort").groupby("candidate_id", sort=False).tail(1).set_index("candidate_id")
    child_latest = child_history.sort_values("date", kind="mergesort").groupby("combo1_id", sort=False).tail(1).set_index("combo1_id")
    seeds = {
        "c1_raw": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "strategy_risk_state"]) for row in final10.loc[final10["family"].eq("Combo1")].itertuples(index=False)},
        "c1_active": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "active_count"]) for row in final10.loc[final10["family"].eq("Combo1")].itertuples(index=False)},
        "c2_raw": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "strategy_risk_state"]) for row in final10.loc[final10["family"].eq("Combo2")].itertuples(index=False)},
        "c2_active": {str(row.candidate_id): int(latest.loc[str(row.candidate_id), "active_count"]) for row in final10.loc[final10["family"].eq("Combo2")].itertuples(index=False)},
        "child_raw": {str(index): int(row["raw_risk_state"]) for index, row in child_latest.iterrows()},
    }
    return history, seeds


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
    panel, registry, final10, children, manifest, raw_seed, combo2_reference = _load()
    core = _overlay_authoritative_raw(panel, replay_core(panel, registry), raw_seed)
    dates, _mask, eval_start, eval_end, _returns = performance_calendar(panel)
    authoritative_t1 = _authoritative_final_states(combo2_reference, dates[eval_start : eval_end + 1])
    history, seeds = _history_and_seeds(panel, final10, children, core, authoritative_t1)
    cutoff = pd.Timestamp(panel["date"].max()).normalize()
    snapshot = _snapshot(final10, history, panel, status="FROZEN_ONLY")
    metrics = replay_final10(panel, final10, children, core, authoritative_t1=authoritative_t1)
    return {
        "runtime_mode": "FROZEN_ONLY", "network_access": False, "basis_date": _date(cutoff), "frozen_cutoff": _date(cutoff),
        "proxy_only": True, "direct_oas_used": False, "asset_manifest_sha256": asset_sha256(OPERATIONAL_MANIFEST),
        "snapshot": snapshot, "metrics": metrics, "history": history, "panel": panel, "registry": registry, "final10": final10,
        "children": children, "seeds": seeds, "core": core, "raw_seed": raw_seed,
        "authoritative_t1": authoritative_t1,
    }
