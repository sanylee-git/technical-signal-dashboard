from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .engine import D1C1Context, read_json


def build_final9_snapshot(
    ctx: D1C1Context,
    final9_live: pd.DataFrame,
    source_status: pd.DataFrame,
    transformed: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    metrics = pd.read_csv(ctx.asset_dir / "kospi_final9_candidate_metrics.csv")
    slot = dict(zip(metrics["candidate_id"], metrics["slot"]))
    role = dict(zip(metrics["candidate_id"], metrics.get("role", metrics["model_type"])))
    suffix = dict(zip(metrics["candidate_id"], metrics.get("suffix", metrics["candidate_id"])))
    dictionary = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    transformed_dates = pd.to_datetime(transformed["date"]).dt.strftime("%Y-%m-%d")
    frozen_reference_end = transformed_dates.loc[~transformed.get("live_extension_row", False).astype(bool)].max()
    live_dates = transformed_dates.loc[transformed.get("live_extension_row", False).astype(bool)]
    live_extension_start = live_dates.min() if len(live_dates) else None

    rows: list[dict[str, Any]] = []
    for candidate_id, one in final9_live.groupby("candidate_id", sort=False):
        one = one.sort_values("date").reset_index(drop=True)
        calculable = one.loc[one["valid_signal"].astype(bool)].copy()
        if calculable.empty:
            latest = one.iloc[-1]
            basis_date = None
            calc = False
        else:
            latest = calculable.iloc[-1]
            basis_date = pd.to_datetime(latest["date"]).strftime("%Y-%m-%d")
            calc = True
        state_start, state_days = _current_state_span(calculable)
        last_start = _last_event_date(calculable, "risk_start_signal")
        last_end = _last_event_date(calculable, "risk_end_signal")
        last_transition = max([d for d in [last_start, last_end] if d is not None], default=None)
        source_min_obs = source_status["latest_observation_date"].dropna().min() if not source_status.empty else None
        source_max_obs = source_status["latest_observation_date"].dropna().max() if not source_status.empty else None
        source_min_avail = source_status["latest_available_date"].dropna().min() if not source_status.empty else None
        source_max_avail = source_status["latest_available_date"].dropna().max() if not source_status.empty else None
        bottleneck = ""
        if not source_status.empty and source_status["latest_available_date"].notna().any():
            bottleneck = source_status.sort_values("latest_available_date")["source_id"].iloc[0]
        component_ids = json.loads(str(latest.get("component_ids_json", "[]")))
        rows.append(
            {
                "candidate_id": candidate_id,
                "suffix": suffix.get(candidate_id, candidate_id[-8:]),
                "model_type": latest["model_type"],
                "role": role.get(candidate_id, ""),
                "calculable": bool(calc),
                "calculation_status": latest.get("calculation_status", "CALCULABLE" if calc else "MISSING_REQUIRED_INPUT"),
                "calculation_reason": latest.get("calculation_reason", ""),
                "requested_as_of": pd.Timestamp.utcnow().isoformat(),
                "basis_date": basis_date,
                "last_calculable_basis_date": basis_date,
                "raw_risk_state": _int_or_none(latest.get("raw_risk_state")),
                "t1_position": _int_or_none(latest.get("t1_position")),
                "t1_valid": bool(latest.get("t1_valid", False)),
                "active_count": _int_or_none(latest.get("active_count")),
                "component_count": int(latest.get("component_count", len(component_ids))),
                "n_or_m": int(latest.get("component_count", len(component_ids))),
                "K": int(latest.get("K")),
                "L": int(latest.get("L")),
                "active_component_ids": json.dumps(component_ids[: int(latest.get("active_count") or 0)], ensure_ascii=False),
                "inactive_component_ids": json.dumps(component_ids[int(latest.get("active_count") or 0) :], ensure_ascii=False),
                "invalid_component_ids": "[]",
                "new_start_signal": _int_or_none(latest.get("risk_start_signal")),
                "new_end_signal": _int_or_none(latest.get("risk_end_signal")),
                "last_start_date": last_start,
                "last_end_date": last_end,
                "last_transition_date": last_transition,
                "current_state_start_date": state_start,
                "current_state_trading_days": state_days,
                "source_min_latest_observation_date": source_min_obs,
                "source_max_latest_observation_date": source_max_obs,
                "source_min_latest_available_date": source_min_avail,
                "source_max_latest_available_date": source_max_avail,
                "source_bottleneck_id": bottleneck,
                "frozen_reference_end": frozen_reference_end,
                "live_extension_start": live_extension_start,
                "freshness_status": "NOT_EVALUATED",
                "stale_status": "NOT_EVALUATED",
                "shadow_mode": True,
                "official_operating_model": False,
            }
        )
    snap = pd.DataFrame(rows).sort_values(["model_type", "candidate_id"]).reset_index(drop=True)
    summary = _group_summary(snap)
    return snap, summary


def _current_state_span(frame: pd.DataFrame) -> tuple[str | None, int | None]:
    if frame.empty:
        return None, None
    raw = frame["raw_risk_state"].astype("Int8")
    latest_state = raw.iloc[-1]
    dates = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d").tolist()
    start_idx = len(raw) - 1
    for i in range(len(raw) - 2, -1, -1):
        if pd.isna(raw.iloc[i]) or int(raw.iloc[i]) != int(latest_state):
            break
        start_idx = i
    return dates[start_idx], len(raw) - start_idx


def _last_event_date(frame: pd.DataFrame, col: str) -> str | None:
    if frame.empty or col not in frame:
        return None
    hit = frame.loc[frame[col].fillna(0).astype(int).eq(1)]
    if hit.empty:
        return None
    return pd.to_datetime(hit["date"].iloc[-1]).strftime("%Y-%m-%d")


def _int_or_none(value: object) -> int | None:
    if pd.isna(value):
        return None
    return int(value)


def _group_summary(snapshot: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model_type, expected in [("combo1", 4), ("combo2", 5)]:
        group = snapshot.loc[snapshot["model_type"].eq(model_type)].copy()
        basis = group["basis_date"].dropna().unique().tolist()
        out[model_type] = {
            "total_count": expected,
            "calculable_count": int(group["calculable"].sum()),
            "uncalculable_count": int(expected - group["calculable"].sum()),
            "risk_off_count": int(group.loc[group["calculable"], "raw_risk_state"].fillna(0).astype(int).sum()),
            "risk_on_count": int(group["calculable"].sum() - group.loc[group["calculable"], "raw_risk_state"].fillna(0).astype(int).sum()),
            "common_basis_date": basis[0] if len(basis) == 1 else None,
            "candidate_basis_dates": dict(zip(group["candidate_id"], group["basis_date"])),
        }
    return out
