from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .canonical_registry import build_canonical_registry, consistency_from_registry
from .engine import D1C1Context, read_json, sha256_file, sha256_text
from .environment_fingerprint import environment_fingerprint
from .freshness import evaluate_source_freshness
from .freshness_snapshot import final9_required_sources, qualify_candidates
from .krx_calendar import kospi_completed_sessions, kospi_latest_allowed_live_session, kospi_latest_completed_session
from .live_availability import build_transformed_frame
from .live_contracts import SOURCE_CONTRACTS
from .live_engine import compute_live_tree
from .live_sources import fetch_source
from .live_tail import source_status_rows
from .provider_dates import normalize_provider_dates_for_freshness
from .retry import fetch_with_optional_bypass
from .snapshot import build_final9_snapshot


def cloud_probe_contract() -> dict[str, Any]:
    return {
        "probe_name": "kospi_macro5_d1c2a_cloud_probe",
        "output_mode": "JSON",
        "cloud_probe_executed_in_d1c2a": False,
        "source_compare_keys": [
            "source_id",
            "actual_latest_observation_date",
            "actual_latest_available_date",
            "selected_route",
            "final_freshness_status",
        ],
        "candidate_compare_keys": [
            "candidate_id",
            "basis_date",
            "raw_risk_state",
            "t1_position",
            "active_count",
            "freshness_qualified",
        ],
        "environment_compare_keys": [
            "python_version",
            "platform",
            "package_versions",
            "timezone",
            "contract_hashes",
            "runtime_code_hash",
        ],
        "allowed_differences": ["fetched_at_utc", "run_started_at_utc", "run_completed_at_utc"],
        "hard_fail_differences": ["raw_risk_state", "t1_position", "candidate_snapshot_hash"],
    }


def _contract_hashes(ctx: D1C1Context) -> dict[str, str]:
    files = {
        "calendar_asset_hash": ctx.asset_dir / "kospi_d1c2a2r_krx_calendar_asset.parquet",
        "calendar_contract_hash": ctx.asset_dir / "kospi_d1c2a2r_krx_calendar_contract.json",
        "dependency_graph_hash": ctx.asset_dir / "kospi_d1c1_dependency_graph.json",
        "final9_dictionary_hash": ctx.asset_dir / "kospi_final9_component_dictionary.json",
        "core15_metadata_hash": ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet",
        "runtime_dependency_manifest_hash": ctx.asset_dir / "kospi_d1c2b_runtime_dependency_manifest.json",
    }
    return {key: sha256_file(path) for key, path in files.items() if path.exists()}


def run_kospi_macro5_cloud_probe(
    as_of_utc: datetime | None = None,
    *,
    network_enabled: bool = True,
    lkg_mode: str = "DISABLED",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    as_of_utc = as_of_utc or datetime.now(timezone.utc)
    root = Path(__file__).resolve().parents[1]
    ctx = D1C1Context(root, root.parent / "macro_dashboard_kospi")
    contract_hashes = _contract_hashes(ctx)
    env = environment_fingerprint(root / "kospi_macro5_runtime", contract_hashes=contract_hashes)
    if not network_enabled:
        result = {
            "probe_contract_version": "d1c2b_streamlit_cloud_probe_v1",
            "probe_contract": cloud_probe_contract() | {"output_mode": "JSON"},
            "probe_status": "NETWORK_DISABLED",
            "as_of_utc": as_of_utc.isoformat(),
            "environment_fingerprint": env,
            "errors": ["network_enabled=false"],
        }
        return result

    frozen_path = ctx.asset_dir / "kospi_d1c1a2_availability_adjusted_transformed_source_base.parquet"
    if not frozen_path.exists():
        frozen_path = ctx.asset_dir / "kospi_d1c1a1_frozen_raw_source_base.parquet"
    frozen = pd.read_parquet(frozen_path)
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    latest_krx = kospi_latest_completed_session(as_of_utc)
    latest_kospi_live = kospi_latest_allowed_live_session(as_of_utc)
    session_end = latest_kospi_live or latest_krx
    sessions_df = kospi_completed_sessions("2024-01-01", session_end, as_of_utc)
    sessions = pd.DatetimeIndex(pd.to_datetime(sessions_df["session_date"])).normalize()

    raw_frames = {}
    source_rows = []
    selected_frames = {}
    provider_date_rows = []
    retry_rows = []
    for sid, contract in SOURCE_CONTRACTS.items():
        raw, attempts, retry_meta = fetch_with_optional_bypass(
            contract,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
            latest_allowed_kospi_session=latest_kospi_live,
            fetcher=fetch_source,
        )
        raw_frames[sid] = raw
        retry_rows.extend(attempts)
        initial = evaluate_source_freshness(
            contract,
            raw,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
            latest_allowed_kospi_session=latest_kospi_live,
        )
        selected, date_audit = normalize_provider_dates_for_freshness(
            contract,
            raw,
            expected_latest_observation_date=initial.expected_latest_observation_date,
            latest_completed_krx_session=None if latest_krx is None else latest_krx.strftime("%Y-%m-%d"),
            latest_allowed_kospi_session=None if latest_kospi_live is None else latest_kospi_live.strftime("%Y-%m-%d"),
        )
        selected_frames[sid] = selected
        provider_date_rows.append(date_audit)
        evaluation = evaluate_source_freshness(
            contract,
            selected,
            as_of_utc=as_of_utc,
            krx_sessions=sessions,
            latest_completed_krx=latest_krx,
            latest_allowed_kospi_session=latest_kospi_live,
        )
        source_rows.append(
            {
                "source_id": sid,
                "provider": contract.provider,
                "provider_series_id": contract.provider_series_id,
                "raw_latest_observation_date": date_audit["raw_latest_observation_date"],
                "selected_latest_observation_date": date_audit["selected_latest_observation_date"],
                "actual_latest_observation_date": evaluation.actual_latest_observation_date,
                "actual_latest_available_date": evaluation.actual_latest_available_date,
                "latest_available_date": evaluation.actual_latest_available_date,
                "latest_krx_aligned_date": evaluation.actual_latest_krx_aligned_date,
                "expected_latest_observation_date": evaluation.expected_latest_observation_date,
                "expected_latest_available_date": evaluation.expected_latest_available_date,
                "expected_latest_krx_aligned_date": evaluation.expected_latest_krx_aligned_date,
                "lag_krx_sessions": evaluation.lag_krx_sessions,
                "allowed_partial_row_count": date_audit.get("allowed_partial_row_count", 0),
                "excluded_partial_row_count": date_audit.get("excluded_partial_row_count", 0),
                "kospi_partial_daily_allowed": date_audit.get("kospi_partial_daily_allowed", False),
                "kospi_latest_row_final": date_audit.get("kospi_latest_row_final"),
                "kospi_live_observation_type": date_audit.get("kospi_live_observation_type", ""),
                "freshness_status": evaluation.final_freshness_status,
                "fetch_status": selected["status"].iloc[0] if not selected.empty and "status" in selected else "FETCH_ERROR",
                "selected_route": selected["source_route"].iloc[0] if not selected.empty and "source_route" in selected else "",
                "selected_attempt": retry_meta["selected_attempt"],
                "data_hash": sha256_text(selected.tail(256).to_csv(index=False)) if not selected.empty else "",
                "tail_hash": sha256_text(selected.tail(20).to_csv(index=False)) if not selected.empty else "",
                "row_count": int(len(selected.loc[selected.get("valid", False).astype(bool)])) if not selected.empty else 0,
            }
        )

    source_df = pd.DataFrame(source_rows)
    registry, consumers = build_canonical_registry(selected_frames)
    consistency = consistency_from_registry(consumers)
    lag_policy = {sid: contract.lag_bdays for sid, contract in SOURCE_CONTRACTS.items()}
    transformed, latest_available = build_transformed_frame(frozen, selected_frames, lag_policy)
    live = compute_live_tree(ctx, transformed)
    source_status = source_status_rows(selected_frames, frozen, latest_available)
    snapshot, _ = build_final9_snapshot(ctx, live["final9"], source_status, transformed)
    candidate_freshness, group_summary = qualify_candidates(snapshot, source_df.rename(columns={"freshness_status": "final_freshness_status"}), consistency.rename(columns={"rule_id": "rule_id"}), final9_required_sources(ctx))
    candidate_rows = candidate_freshness[
        [
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
            "freshness_status",
            "blocked_source_ids",
            "new_start_signal",
            "new_end_signal",
            "current_state_start_date",
            "current_state_trading_days",
        ]
    ].to_dict("records")
    candidate_semantic_rows = candidate_freshness[
        [
            "candidate_id",
            "basis_date",
            "calculable",
            "freshness_qualified",
            "raw_risk_state",
            "t1_position",
            "active_count",
            "freshness_status",
            "blocked_source_ids",
        ]
    ].to_dict("records")
    source_hash = sha256_text(pd.DataFrame(source_rows).drop(columns=[], errors="ignore").to_csv(index=False))
    candidate_hash = sha256_text(pd.DataFrame(candidate_semantic_rows).to_csv(index=False))
    full_hash = sha256_text(source_hash + candidate_hash + str(latest_krx) + str(contract_hashes))
    result = {
        "probe_contract_version": "d1c2b_streamlit_cloud_probe_v1",
        "probe_contract": cloud_probe_contract() | {"output_mode": "JSON"},
        "probe_status": "FULL_CLOUD_PROBE_EXECUTED",
        "as_of_utc": as_of_utc.isoformat(),
        "as_of_kst": pd.Timestamp(as_of_utc).tz_convert("Asia/Seoul").isoformat(),
        "environment_fingerprint": env,
        "calendar": {
            "latest_completed_session": None if latest_krx is None else latest_krx.strftime("%Y-%m-%d"),
            "latest_kospi_live_session": None if latest_kospi_live is None else latest_kospi_live.strftime("%Y-%m-%d"),
            "calendar_contract_hash": contract_hashes.get("calendar_contract_hash", ""),
            "calendar_asset_hash": contract_hashes.get("calendar_asset_hash", ""),
        },
        "source_contract": {"source_count": len(SOURCE_CONTRACTS)},
        "sources": source_rows,
        "source_consistency": consistency.to_dict("records"),
        "retry_attempts": retry_rows,
        "candidates": candidate_rows,
        "group_summary": group_summary,
        "hashes": {
            "source_snapshot_hash": source_hash,
            "candidate_snapshot_hash": candidate_hash,
            "candidate_semantic_hash": candidate_hash,
            "full_probe_canonical_hash": full_hash,
            "contract_hashes": contract_hashes,
        },
        "errors": [],
        "warnings": [],
        "lkg_mode": lkg_mode,
    }
    if output_path:
        Path(output_path).write_text(__import__("json").dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
    return result


def run_cloud_probe(as_of_utc: datetime | None = None, output_mode: str = "JSON") -> dict[str, Any]:
    return run_kospi_macro5_cloud_probe(as_of_utc=as_of_utc, network_enabled=True)
