from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .canonical_registry import build_canonical_registry, consistency_from_registry
from .engine import D1C1Context
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
