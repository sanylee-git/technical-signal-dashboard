from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .canonical_registry import build_canonical_registry, consistency_from_registry
from .engine import D1C1Context, read_json
from .freshness import evaluate_source_freshness
from .freshness_snapshot import final9_required_sources, qualify_candidates
from .krx_calendar import kospi_completed_sessions, kospi_latest_completed_session
from .live_availability import build_transformed_frame
from .live_contracts import SOURCE_CONTRACTS
from .live_engine import compute_live_tree
from .live_sources import fetch_source
from .live_tail import source_status_rows
from .provider_dates import normalize_provider_dates_for_freshness
from .retry import fetch_with_optional_bypass
from .snapshot import build_final9_snapshot


def load_macro5_live_page_data(as_of_utc: datetime | None = None) -> dict[str, Any]:
    as_of_utc = as_of_utc or datetime.now(timezone.utc)
    root = Path(__file__).resolve().parents[1]
    ctx = D1C1Context(root, root.parent / "macro_dashboard_kospi")
    frozen = _load_transformed_source_base(ctx)
    latest_krx = kospi_latest_completed_session(as_of_utc)
    sessions_df = kospi_completed_sessions("2024-01-01", latest_krx, as_of_utc)
    sessions = pd.DatetimeIndex(pd.to_datetime(sessions_df["session_date"])).normalize()

    selected_frames: dict[str, pd.DataFrame] = {}
    source_rows: list[dict[str, Any]] = []
    for source_id, contract in SOURCE_CONTRACTS.items():
        raw, attempts, retry_meta = fetch_with_optional_bypass(
            contract,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
            fetcher=fetch_source,
        )
        initial = evaluate_source_freshness(
            contract,
            raw,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
        )
        selected, date_audit = normalize_provider_dates_for_freshness(
            contract,
            raw,
            expected_latest_observation_date=initial.expected_latest_observation_date,
            latest_completed_krx_session=None if latest_krx is None else latest_krx.strftime("%Y-%m-%d"),
        )
        selected_frames[source_id] = selected
        evaluation = evaluate_source_freshness(
            contract,
            selected,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
        )
        source_rows.append(
            {
                "source_id": source_id,
                "provider": contract.provider,
                "provider_series_id": contract.provider_series_id,
                "fetch_status": selected["status"].iloc[0] if not selected.empty and "status" in selected else "FETCH_ERROR",
                "freshness_status": evaluation.final_freshness_status,
                "raw_latest_observation_date": date_audit["raw_latest_observation_date"],
                "selected_latest_observation_date": date_audit["selected_latest_observation_date"],
                "actual_latest_observation_date": evaluation.actual_latest_observation_date,
                "actual_latest_available_date": evaluation.actual_latest_available_date,
                "actual_latest_krx_aligned_date": evaluation.actual_latest_krx_aligned_date,
                "latest_available_date": evaluation.actual_latest_available_date,
                "latest_krx_aligned_date": evaluation.actual_latest_krx_aligned_date,
                "expected_latest_observation_date": evaluation.expected_latest_observation_date,
                "expected_latest_available_date": evaluation.expected_latest_available_date,
                "expected_latest_krx_aligned_date": evaluation.expected_latest_krx_aligned_date,
                "lag_krx_sessions": evaluation.lag_krx_sessions,
                "selected_route": selected["source_route"].iloc[0] if not selected.empty and "source_route" in selected else "",
                "selected_attempt": retry_meta["selected_attempt"],
                "row_count": int(len(selected.loc[selected.get("valid", False).astype(bool)])) if not selected.empty else 0,
            }
        )

    source_df = pd.DataFrame(source_rows)
    _, consumers = build_canonical_registry(selected_frames)
    consistency = consistency_from_registry(consumers)
    lag_policy = {source_id: contract.lag_bdays for source_id, contract in SOURCE_CONTRACTS.items()}
    transformed, latest_available = build_transformed_frame(frozen, selected_frames, lag_policy)
    live = compute_live_tree(ctx, transformed)
    source_status = source_status_rows(selected_frames, frozen, latest_available)
    snapshot, _ = build_final9_snapshot(ctx, live["final9"], source_status, transformed)
    candidate_freshness, group_summary = qualify_candidates(
        snapshot,
        source_df.rename(columns={"freshness_status": "final_freshness_status"}),
        consistency.rename(columns={"rule_id": "rule_id"}),
        final9_required_sources(ctx),
    )
    return {
        "as_of_utc": as_of_utc.isoformat(),
        "expected_latest_krx_session": None if latest_krx is None else latest_krx.strftime("%Y-%m-%d"),
        "sources_count": len(SOURCE_CONTRACTS),
        "sources_reachable_count": int(source_df["fetch_status"].astype(str).str.contains("FETCH_OK|NO_NEW_RELEASE", regex=True).sum()) if not source_df.empty else 0,
        "candidate_rows": _candidate_rows(candidate_freshness),
        "source_rows": source_rows,
        "group_summary": group_summary,
        "core15_component_history": _core15_component_history(live["core15"]),
        "candidate_signal_history": _candidate_signal_history(ctx, live["final9"]),
        "child_combo1_history": _child_combo1_history(live["child_combo1"]),
        "component_signal_history": _component_signal_history(ctx, live),
        "benchmark_close_history": _benchmark_close_history(transformed),
        "calculation_status": "CALCULABLE",
        "error_message": "",
    }


def _load_transformed_source_base(ctx: D1C1Context) -> pd.DataFrame:
    path = ctx.asset_dir / "kospi_d1c1a2_availability_adjusted_transformed_source_base.parquet"
    if not path.exists():
        raise FileNotFoundError(f"KOSPI Macro5 transformed source base missing: {path.name}")
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def _candidate_rows(candidate_freshness: pd.DataFrame) -> list[dict[str, Any]]:
    columns = [
        "candidate_id",
        "model_type",
        "role",
        "basis_date",
        "calculable",
        "freshness_qualified",
        "raw_risk_state",
        "t1_position",
        "active_count",
        "component_count",
        "K",
        "L",
        "new_start_signal",
        "new_end_signal",
        "current_state_start_date",
        "current_state_trading_days",
        "freshness_status",
        "blocked_source_ids",
    ]
    available = [col for col in columns if col in candidate_freshness.columns]
    return candidate_freshness[available].to_dict("records")


def _candidate_signal_history(ctx: D1C1Context, final9_live: pd.DataFrame) -> pd.DataFrame:
    frozen = _read_asset_frame(ctx, "kospi_final9_reference_signals.parquet")
    metrics = pd.read_csv(ctx.asset_dir / "kospi_final9_candidate_metrics.csv")
    slot_by_id = dict(zip(metrics["candidate_id"], metrics["slot"]))
    live = final9_live.copy()
    live["date"] = pd.to_datetime(live["date"]).dt.normalize()
    live["slot"] = live["candidate_id"].map(slot_by_id).astype("Int16")
    if "on_count" not in live:
        live["on_count"] = live.get("active_count")
    live = live[
        [
            "date",
            "candidate_id",
            "model_type",
            "slot",
            "raw_risk_state",
            "on_count",
            "t1_position",
            "risk_start_signal",
            "risk_end_signal",
            "valid_signal",
            "active_count",
        ]
    ].copy()
    return _append_live_tail(frozen, live, ["candidate_id", "date"])


def _core15_component_history(core_live: pd.DataFrame) -> pd.DataFrame:
    if core_live is None or core_live.empty:
        return pd.DataFrame()
    out = core_live.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    columns = [
        "date",
        "component_id",
        "risk_state",
        "risk_start_signal",
        "risk_end_signal",
        "valid_signal",
        "calculation_status",
        "calculation_reason",
    ]
    return out[[col for col in columns if col in out.columns]].sort_values(["component_id", "date"]).reset_index(drop=True)


def _child_combo1_history(child_live: pd.DataFrame) -> pd.DataFrame:
    if child_live is None or child_live.empty:
        return pd.DataFrame()
    out = child_live.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    columns = [
        "date",
        "combo1_id",
        "component_count",
        "active_count",
        "raw_risk_state",
        "risk_start_signal",
        "risk_end_signal",
        "valid_signal",
        "calculation_status",
        "calculation_reason",
    ]
    return out[[col for col in columns if col in out.columns]].sort_values(["combo1_id", "date"]).reset_index(drop=True)


def _component_signal_history(ctx: D1C1Context, live: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frozen = _read_asset_frame(ctx, "kospi_final9_component_reference_signals.parquet")
    final9 = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    metrics = pd.read_csv(ctx.asset_dir / "kospi_final9_candidate_metrics.csv")
    slot_by_id = dict(zip(metrics["candidate_id"], metrics["slot"]))
    meta = (
        frozen.sort_values("date")
        .drop_duplicates(["parent_candidate_id", "component_id"], keep="last")
        .set_index(["parent_candidate_id", "component_id"])
    )
    core = live["core15"].copy()
    child = live["child_combo1"].copy()
    if not core.empty:
        core["date"] = pd.to_datetime(core["date"]).dt.normalize()
    if not child.empty:
        child["date"] = pd.to_datetime(child["date"]).dt.normalize()

    frames: list[pd.DataFrame] = []
    for parent_id, spec in final9.items():
        parent_model_type = str(spec["model_type"])
        for order, component_id in enumerate(spec.get("component_ids", []), start=1):
            if parent_model_type == "combo1":
                source = core.loc[core["component_id"].eq(component_id)].copy()
                value_col = "risk_state"
            else:
                source = child.loc[child["combo1_id"].eq(component_id)].copy()
                value_col = "raw_risk_state"
            if source.empty:
                continue
            template = _component_template(meta, parent_id, component_id)
            part = pd.DataFrame(
                {
                    "date": source["date"],
                    "component_risk_state": source[value_col],
                    "component_active_count": pd.NA,
                    "parent_candidate_id": parent_id,
                    "parent_slot": slot_by_id.get(parent_id),
                    "parent_model_type": parent_model_type,
                    "component_id": component_id,
                    "component_order": order,
                    "component_label": template.get("component_label", component_id),
                    "component_K": template.get("component_K", pd.NA),
                    "component_L": template.get("component_L", pd.NA),
                    "valid_signal": source.get("valid_signal", pd.Series(True, index=source.index)),
                    "reference_type": template.get("reference_type", ""),
                }
            )
            frames.append(part)
    live_components = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return _append_live_tail(frozen, live_components, ["parent_candidate_id", "component_id", "date"])


def _benchmark_close_history(transformed: pd.DataFrame) -> pd.DataFrame:
    out = transformed[["date", "kospi_close"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.drop_duplicates(["date"], keep="first").sort_values("date").reset_index(drop=True)


def _read_asset_frame(ctx: D1C1Context, filename: str) -> pd.DataFrame:
    frame = pd.read_parquet(ctx.asset_dir / filename)
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def _append_live_tail(frozen: pd.DataFrame, live: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    frozen = frozen.copy()
    live = live.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    live["date"] = pd.to_datetime(live["date"]).dt.normalize()
    cutoff = frozen["date"].max()
    tail = live.loc[live["date"] > cutoff].copy()
    if tail.empty:
        return frozen.sort_values(key_cols).drop_duplicates(key_cols, keep="first").reset_index(drop=True)
    columns = list(dict.fromkeys([*frozen.columns.tolist(), *tail.columns.tolist()]))
    frozen_aligned = frozen.reindex(columns=columns)
    tail_aligned = tail.reindex(columns=columns)
    all_na_columns = [
        column
        for column in columns
        if frozen_aligned[column].isna().all() and tail_aligned[column].isna().all()
    ]
    concat_columns = [column for column in columns if column not in all_na_columns]
    combined = pd.concat([frozen_aligned[concat_columns], tail_aligned[concat_columns]], ignore_index=True)
    for column in all_na_columns:
        combined[column] = pd.NA
    combined = combined.reindex(columns=columns)
    return combined.sort_values(key_cols).drop_duplicates(key_cols, keep="first").reset_index(drop=True)


def _component_template(meta: pd.DataFrame, parent_id: str, component_id: str) -> dict[str, Any]:
    try:
        row = meta.loc[(parent_id, component_id)]
        return row.to_dict()
    except KeyError:
        return {}
