"""Presentation-only payload for the independent NASDAQ Macro8 Frozen runtime.

This module may derive display frames from the verified Frozen runtime, but it
has no Streamlit, cache, session, provider, or network dependency.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .frozen_replay import (
    EVALUATION_END,
    EVALUATION_START,
    _metrics,
    performance_calendar,
    replay_combo1_raw_history,
    replay_core_chart_history,
)


def _date(value: object) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _normalized(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.sort_values("date", kind="mergesort").reset_index(drop=True)


def _final20(final: pd.DataFrame) -> pd.DataFrame:
    out = final.copy().sort_values("display_order", kind="mergesort").reset_index(drop=True)
    out["model_family"] = out["family"].str.upper()
    out["display_slot"] = out.groupby("model_family", sort=False).cumcount() + 1
    out["display_role"] = out["role"].astype(str)
    return out


def _candidate_history(runtime: dict[str, Any]) -> pd.DataFrame:
    out = _normalized(runtime["history"])
    out = out.rename(columns={"strategy_risk_state": "raw_risk_state", "valid": "valid_signal"})
    return out


def _component_history(runtime: dict[str, Any], final: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = runtime["panel"]
    registry = runtime["registry"].set_index("candidate_id")
    core = runtime["core"]
    children = runtime["children"]
    core_chart = replay_core_chart_history(panel, runtime["registry"])
    core_states = core_chart[["component_id", "date", "risk_state", "risk_start", "risk_end", "valid_signal"]].copy()
    child_history = replay_combo1_raw_history(panel, children, core, evaluation_end=pd.Timestamp(runtime["basis_date"]))
    parts: list[pd.DataFrame] = []

    for parent in final.itertuples(index=False):
        parent_id = str(parent.candidate_id)
        if parent.model_family == "COMBO1":
            for order, component_id in enumerate(str(parent.component_ids_key).split("|"), start=1):
                detail = core_states.loc[core_states["component_id"].eq(component_id)].copy()
                meta = registry.loc[component_id]
                detail = detail.rename(columns={"risk_state": "component_risk_state", "valid_signal": "component_valid"})
                detail.insert(0, "parent_candidate_id", parent_id)
                detail["component_id"] = component_id
                detail.insert(2, "component_order", order)
                detail.insert(3, "component_kind", "CORE_INDICATOR")
                detail.insert(4, "component_label", f"{meta['indicator_name']} · {component_id.split('__')[-2]}")
                parts.append(detail)
        else:
            mapping = children.loc[children["parent_candidate_id"].eq(parent_id)].sort_values("child_order", kind="mergesort")
            for child in mapping.itertuples(index=False):
                detail = child_history.loc[child_history["combo1_id"].eq(child.child_canonical_parent_id)].copy()
                detail = detail.rename(columns={"raw_risk_state": "component_risk_state", "valid": "component_valid"})
                detail.insert(0, "parent_candidate_id", parent_id)
                detail.insert(1, "component_id", str(child.child_canonical_parent_id))
                detail.insert(2, "component_order", int(child.child_order))
                detail.insert(3, "component_kind", "CHILD_COMBO1_RAW_STATE")
                detail.insert(4, "component_label", f"[조합1] 구성 후보 (지표 {int(child.child_n)}개/K{int(child.child_K)}/L{int(child.child_L)})")
                parts.append(detail)
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), core_chart


def _benchmark_history(panel: pd.DataFrame, final: pd.DataFrame, basis_date: object) -> pd.DataFrame:
    base = _normalized(panel[["date", "ndx_close"]])
    base = base.loc[base["date"].between(EVALUATION_START, pd.Timestamp(basis_date).normalize())]
    parts = []
    for candidate_id in final["candidate_id"].astype(str):
        part = base.copy()
        part.insert(0, "candidate_id", candidate_id)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def _display_metrics(runtime: dict[str, Any], final: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    # Official comparison values stay anchored to the verified Frozen evaluation window.
    panel = runtime.get("frozen_panel", runtime["panel"])
    history_source = runtime.get("frozen_history", runtime["history"])
    dates, _mask, evaluation_start, evaluation_end, returns = performance_calendar(panel)
    cutoff = dates[evaluation_end]
    ten_start = int(np.flatnonzero(dates >= cutoff - pd.DateOffset(years=10))[0])
    windows = {"10Y": ten_start, "FULL": evaluation_start}
    history = _candidate_history({"history": history_source})
    rows: list[dict[str, object]] = []
    hold_rows: list[dict[str, object]] = []
    for window, start in windows.items():
        n = evaluation_end - start + 1
        hold_rows.append({"candidate_id": "NASDAQ_HOLD", "window": window, **_metrics(np.zeros(n, dtype=bool), returns[start:evaluation_end + 1], dates[start:evaluation_end + 1], 1.0)})
    for candidate_id in final["candidate_id"].astype(str):
        state = history.loc[history["candidate_id"].eq(candidate_id)].sort_values("date")["raw_risk_state"].to_numpy(dtype=np.int8)
        previous = history.loc[history["candidate_id"].eq(candidate_id)].sort_values("date")["previous_strategy_risk_state"].to_numpy(dtype=np.int8)
        for window, start in windows.items():
            relative_start = start - evaluation_start
            relative_end = evaluation_end - evaluation_start
            prior_state = previous[0] if relative_start == 0 else state[relative_start - 1]
            prior = float(~prior_state.astype(bool))
            rows.append({
                "candidate_id": candidate_id,
                "window": window,
                **_metrics(
                    state[relative_start : relative_end + 1].astype(bool),
                    returns[start : evaluation_end + 1],
                    dates[start : evaluation_end + 1],
                    prior,
                ),
            })
    metrics = pd.DataFrame(rows)
    hold = pd.DataFrame(hold_rows)
    for frame in (metrics, hold):
        frame["asset"] = 100.0 * (1.0 + pd.to_numeric(frame["total_return"], errors="coerce"))
    return metrics, hold, {
        "evaluation_start": _date(dates[evaluation_start]),
        "frozen_cutoff": _date(cutoff),
        "ten_year_start": _date(dates[ten_start]),
    }


def build_presentation_payload(runtime: dict[str, Any]) -> dict[str, Any]:
    """Build chart/table payload from one NASDAQ-owned Frozen or Live runtime."""
    if runtime.get("runtime_mode") not in {"FROZEN_ONLY", "LIVE_TAIL"}:
        raise RuntimeError("NASDAQ Macro8 presentation runtime contract failed")
    final = _final20(runtime["final20"])
    snapshot = runtime["snapshot"].copy().set_index("candidate_id").reindex(final["candidate_id"]).reset_index()
    snapshot["model_family"] = final["model_family"].to_numpy()
    snapshot["display_slot"] = final["display_slot"].to_numpy()
    snapshot["display_role"] = final["display_role"].to_numpy()
    snapshot["status"] = np.where(snapshot["calculable"], "USABLE", "UNAVAILABLE")
    snapshot["raw_risk_state"] = snapshot["strategy_risk_state"].astype("Int64")
    snapshot["week_ago_raw_risk_state"] = snapshot["week_ago_strategy_risk_state"].astype("Int64")
    snapshot["invest_position"] = 1 - snapshot["raw_risk_state"].fillna(1).astype(int)
    snapshot["current_risk_start_date"] = snapshot["current_state_start_date"]
    candidate_history = _candidate_history(runtime)
    component_history, component_chart_history = _component_history(runtime, final)
    metrics, hold, windows = _display_metrics(runtime, final)
    return {
        "presentation_contract": "nasdaq_macro8_live_presentation_payload_v1" if runtime.get("runtime_mode") == "LIVE_TAIL" else "nasdaq_macro8_frozen_presentation_payload_v1",
        "runtime_mode": runtime["runtime_mode"],
        "network_access": bool(runtime.get("network_access")),
        "proxy_only": True,
        "direct_oas_used": False,
        "snapshot": snapshot,
        "candidate_history": candidate_history,
        "component_history": component_history,
        "component_chart_history": component_chart_history,
        "benchmark_history": _benchmark_history(runtime["panel"], final, runtime["basis_date"]),
        "frozen_display_metrics": metrics,
        "benchmark_display_metrics": hold,
        "backtest_windows": windows,
        "live_metrics": runtime["metrics"].copy(),
        "final20": final,
        "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE",
        "final_t1_application_count": 1,
        "ui_side_model_calculation_count": 0,
    }
