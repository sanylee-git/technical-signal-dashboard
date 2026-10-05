from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard_role_aware_market_stage import (
    TIMEPOINTS,
    compute_role_aware_market_outputs,
    load_role_metadata,
    validate_market_metadata,
)
from dashboard_role_aware_stage import classify_role_combo
from dashboard_timepoints import candidate_history_rows_at_offsets

from .canonical_registry import build_canonical_registry, consistency_from_registry
from .engine import D1C1Context, read_json
from .freshness import evaluate_source_freshness
from .freshness_snapshot import final9_required_sources, qualify_candidates
from .krx_calendar import kospi_completed_sessions, kospi_latest_allowed_live_session, kospi_latest_completed_session
from .live_availability import build_transformed_frame
from .live_contracts import SOURCE_CONTRACTS
from .live_contracts import RESOLVER_SOURCE_CONTRACTS
from .live_engine import compute_live_tree
from .live_sources import fetch_naver_kospi_ohlcv, fetch_source
from .live_tail import source_status_rows
from .provider_dates import normalize_provider_dates_for_freshness
from .retry import fetch_with_optional_bypass
from .snapshot import build_final9_snapshot
from live_source_resolver import exact_date_spread, resolve_aligned_sources


FRED_SOURCE_MAX_WORKERS = 4


def load_macro5_live_page_data(as_of_utc: datetime | None = None) -> dict[str, Any]:
    as_of_utc = as_of_utc or datetime.now(timezone.utc)
    root = Path(__file__).resolve().parents[1]
    ctx = D1C1Context(root, root.parent / "macro_dashboard_kospi")
    operating_dictionary = read_json(ctx.asset_dir / "kospi_final5_operating_dictionary.json")
    component_additions = read_json(ctx.asset_dir / "kospi_final5_component_metadata_additions.json")["components"]
    metrics = pd.concat(
        [
            pd.read_csv(ctx.asset_dir / "kospi_final9_candidate_metrics.csv"),
            pd.read_csv(ctx.asset_dir / "kospi_final5_additional_candidate_metrics.csv"),
        ],
        ignore_index=True,
        sort=False,
    )
    frozen = _load_transformed_source_base(ctx)
    latest_krx = kospi_latest_completed_session(as_of_utc)
    latest_kospi_live = kospi_latest_allowed_live_session(as_of_utc)
    session_end = latest_kospi_live or latest_krx
    sessions_df = kospi_completed_sessions("2024-01-01", session_end, as_of_utc)
    sessions = pd.DatetimeIndex(pd.to_datetime(sessions_df["session_date"])).normalize()

    selected_frames, source_rows, resolver_frames = _load_source_frames(
        as_of_utc=as_of_utc,
        sessions=sessions,
        latest_krx=latest_krx,
        latest_kospi_live=latest_kospi_live,
    )

    source_df = pd.DataFrame(source_rows)
    _, consumers = build_canonical_registry(selected_frames)
    consistency = consistency_from_registry(consumers)
    lag_policy = {source_id: contract.lag_bdays for source_id, contract in SOURCE_CONTRACTS.items()}
    transformed, latest_available = build_transformed_frame(frozen, selected_frames, lag_policy)
    resolver_log, resolver_status = _apply_live_source_resolver(transformed, frozen, selected_frames, resolver_frames)
    live = compute_live_tree(ctx, transformed, operating_dictionary)
    source_status = source_status_rows(selected_frames, frozen, latest_available)
    snapshot, _ = build_final9_snapshot(
        ctx,
        live["operating_final10"],
        source_status,
        transformed,
        candidate_metrics=metrics,
        candidate_dictionary={row["candidate_id"]: row for row in operating_dictionary["candidates"]},
    )
    candidate_freshness, group_summary = qualify_candidates(
        snapshot,
        source_df.rename(columns={"freshness_status": "final_freshness_status"}),
        consistency.rename(columns={"rule_id": "rule_id"}),
        final9_required_sources(
            ctx,
            candidate_dictionary={row["candidate_id"]: row for row in operating_dictionary["candidates"]},
            additional_metadata=component_additions,
        ),
    )
    candidate_history = _candidate_signal_history(ctx, live["operating_final10"], metrics)
    component_history = _component_signal_history(ctx, live, operating_dictionary, metrics)
    official_history, official_snapshot, individual_timepoints, role_outputs, red_contract = _role_aware_outputs(
        candidate_freshness,
        candidate_history,
        operating_dictionary,
    )
    return {
        "as_of_utc": as_of_utc.isoformat(),
        "expected_latest_krx_session": None if latest_krx is None else latest_krx.strftime("%Y-%m-%d"),
        "latest_kospi_live_session": None if latest_kospi_live is None else latest_kospi_live.strftime("%Y-%m-%d"),
        "sources_count": len(SOURCE_CONTRACTS),
        "sources_reachable_count": int(source_df["fetch_status"].astype(str).str.contains("FETCH_OK|NO_NEW_RELEASE", regex=True).sum()) if not source_df.empty else 0,
        "candidate_rows": _candidate_rows(candidate_freshness),
        "operating_candidates": pd.DataFrame(operating_dictionary["candidates"]),
        "operating_candidate_metrics": metrics,
        "role_aware_snapshot": official_snapshot,
        "official_t1_candidate_history": official_history,
        "role_aware_stage_outputs": role_outputs,
        "role_metadata_validation": pd.DataFrame(
            validate_market_metadata(
                "KOSPI",
                pd.DataFrame(
                    [
                        {"candidate_id": row["candidate_id"], "model_family": row["model_type"].upper()}
                        for row in operating_dictionary["candidates"]
                    ]
                ),
                load_role_metadata(),
            )
        ),
        "individual_four_timepoint_outputs": individual_timepoints,
        "red_contract_qa": red_contract,
        "source_rows": source_rows,
        "source_resolver_status": resolver_status,
        "source_resolver_log": resolver_log,
        "group_summary": group_summary,
        "core15_component_history": _core15_component_history(live["core15"]),
        "candidate_signal_history": candidate_history,
        "child_combo1_history": _child_combo1_history(live["child_combo1"]),
        "component_signal_history": component_history,
        "benchmark_close_history": _benchmark_close_history(transformed),
        "transformed_source_history": _transformed_source_history(transformed),
        "calculation_status": "CALCULABLE",
        "error_message": "",
    }


def _load_source_frames(
    *,
    as_of_utc: datetime,
    sessions: pd.DatetimeIndex,
    latest_krx: pd.Timestamp,
    latest_kospi_live: pd.Timestamp | None,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], dict[str, pd.DataFrame]]:
    results: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
    fred_items = [(source_id, contract) for source_id, contract in SOURCE_CONTRACTS.items() if contract.provider == "fred"]
    non_fred_items = [(source_id, contract) for source_id, contract in SOURCE_CONTRACTS.items() if contract.provider != "fred"]

    for source_id, contract in non_fred_items:
        results[source_id] = _load_one_source_frame(
            source_id=source_id,
            contract=contract,
            as_of_utc=as_of_utc,
            sessions=sessions,
            latest_krx=latest_krx,
            latest_kospi_live=latest_kospi_live,
        )

    with ThreadPoolExecutor(max_workers=FRED_SOURCE_MAX_WORKERS) as executor:
        future_by_source = {
            source_id: executor.submit(
                _load_one_source_frame,
                source_id=source_id,
                contract=contract,
                as_of_utc=as_of_utc,
                sessions=sessions,
                latest_krx=latest_krx,
                latest_kospi_live=latest_kospi_live,
            )
            for source_id, contract in fred_items
        }
        for source_id, _contract in fred_items:
            results[source_id] = future_by_source[source_id].result()

    selected_frames = {source_id: results[source_id][0] for source_id in SOURCE_CONTRACTS}
    source_rows = [results[source_id][1] for source_id in SOURCE_CONTRACTS]
    resolver_results: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=FRED_SOURCE_MAX_WORKERS) as executor:
        future_by_source = {
            source_id: executor.submit(
                _load_resolver_source_frame,
                contract=contract,
                as_of_utc=as_of_utc,
            )
            for source_id, contract in RESOLVER_SOURCE_CONTRACTS.items()
        }
        for source_id in RESOLVER_SOURCE_CONTRACTS:
            resolver_results[source_id] = future_by_source[source_id].result()
    return selected_frames, source_rows, {source_id: result[0] for source_id, result in resolver_results.items()}


def _load_resolver_source_frame(*, contract, as_of_utc: datetime) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = fetch_source(contract, cache_mode="NORMAL", as_of_utc=as_of_utc)
    valid = frame.loc[frame.get("valid", pd.Series(False, index=frame.index)).astype(bool)] if not frame.empty else frame
    latest = pd.to_datetime(valid["observation_date"], errors="coerce").dropna().max() if not valid.empty else pd.NaT
    return frame, {
        "source_id": contract.source_id,
        "provider": contract.provider,
        "provider_series_id": contract.provider_series_id,
        "fetch_status": frame["status"].iloc[0] if not frame.empty and "status" in frame else "FETCH_ERROR",
        "latest_observation_date": None if pd.isna(latest) else pd.Timestamp(latest).strftime("%Y-%m-%d"),
    }


def _apply_live_source_resolver(
    transformed: pd.DataFrame,
    frozen: pd.DataFrame,
    selected_frames: dict[str, pd.DataFrame],
    resolver_frames: dict[str, pd.DataFrame],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dates = pd.DatetimeIndex(pd.to_datetime(transformed["date"]).dt.normalize())
    cutoff = pd.Timestamp(frozen["date"].max()).normalize()
    candidates = {
        "10Y-2Y": {
            "FRED_T10Y2Y": resolver_frames.get("resolver_t10y2y", pd.DataFrame()),
            "DERIVED_DGS10_MINUS_DGS2": exact_date_spread(
                selected_frames.get("us_10y_yield", pd.DataFrame()),
                selected_frames.get("us_2y_yield", pd.DataFrame()),
                "DERIVED_DGS10_MINUS_DGS2",
            ),
        },
        "10Y-3M": {
            "FRED_T10Y3M": resolver_frames.get("resolver_t10y3m", pd.DataFrame()),
            "DERIVED_DGS10_MINUS_DGS3MO": exact_date_spread(
                selected_frames.get("us_10y_yield", pd.DataFrame()),
                selected_frames.get("us_3m_yield", pd.DataFrame()),
                "DERIVED_DGS10_MINUS_DGS3MO",
            ),
        },
        "VIX3M": {
            "CBOE_VIX3M": resolver_frames.get("resolver_cboe_vix3m", pd.DataFrame()),
            "FRED_VXVCLS": selected_frames.get("vix3m", pd.DataFrame()),
        },
    }
    primaries = {"10Y-2Y": "FRED_T10Y2Y", "10Y-3M": "FRED_T10Y3M", "VIX3M": "CBOE_VIX3M"}
    logs: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    resolved: dict[str, pd.DataFrame] = {}
    for logical, pair in candidates.items():
        output, status = resolve_aligned_sources(
            dates, pair, primary_source=primaries[logical], lag=1,
            calendar_mode="business_day", tolerance=1e-8 if logical.startswith("10Y") else 0.0,
            after_date=cutoff,
        )
        output["logical_series"] = logical
        status.update({"tab": "KOSPI", "logical_series": logical})
        logs.extend(output.to_dict("records"))
        statuses.append(status)
        resolved[logical] = output.set_index("date")

    tail = pd.to_datetime(transformed["date"]).dt.normalize().gt(cutoff)
    for logical, column in (("10Y-2Y", "us_10y_2y_spread"), ("10Y-3M", "us_10y_3m_spread")):
        values = resolved[logical]["value"].reindex(dates).to_numpy()
        transformed.loc[tail, column] = values[tail.to_numpy()]
    vix3m = resolved["VIX3M"]["value"].reindex(dates).to_numpy()
    transformed.loc[tail, "vix3m"] = vix3m[tail.to_numpy()]
    transformed.loc[tail, "vix_spread"] = transformed.loc[tail, "vix"].to_numpy() - transformed.loc[tail, "vix3m"].to_numpy()
    transformed.loc[tail, "vix_spread_safe"] = -transformed.loc[tail, "vix_spread"].to_numpy()
    return logs, statuses


def _load_one_source_frame(
    *,
    source_id: str,
    contract,
    as_of_utc: datetime,
    sessions: pd.DatetimeIndex,
    latest_krx: pd.Timestamp,
    latest_kospi_live: pd.Timestamp | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw, attempts, retry_meta = fetch_with_optional_bypass(
        contract,
        as_of_utc=as_of_utc,
        krx_sessions=sessions,
        latest_completed_krx=latest_krx,
        latest_allowed_kospi_session=latest_kospi_live,
        fetcher=fetch_source,
    )
    if source_id == "kospi_ohlcv":
        latest_valid = _latest_valid_source_date(raw)
        if latest_krx is not None and (latest_valid is None or latest_valid < pd.Timestamp(latest_krx).normalize()):
            fallback = fetch_naver_kospi_ohlcv(contract, as_of_utc=as_of_utc)
            fallback_latest = _latest_valid_source_date(fallback)
            if fallback_latest is not None and fallback_latest >= pd.Timestamp(latest_krx).normalize():
                raw = fallback
                attempts.append(
                    {
                        "source_id": source_id,
                        "attempt_number": "NAVER_FALLBACK",
                        "cache_mode": "AUTHORIZED_FALLBACK",
                        "source_route": fallback["source_route"].iloc[0] if not fallback.empty else "",
                        "row_count": int(fallback.get("valid", pd.Series(dtype=bool)).astype(bool).sum()),
                        "latest_observation_date": fallback_latest.strftime("%Y-%m-%d"),
                        "status": fallback["status"].iloc[0] if not fallback.empty else "FETCH_ERROR",
                        "freshness_status": "FRESH",
                        "error": "",
                    }
                )
                retry_meta = {
                    **retry_meta,
                    "selected_attempt": "NAVER_FALLBACK",
                    "selected_reason": "AUTHORIZED_NAVER_FALLBACK_FOR_MISSING_OR_INVALID_LATEST_KRX_ROW",
                }
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
    evaluation = evaluate_source_freshness(
        contract,
        selected,
        as_of_utc=as_of_utc,
        krx_sessions=sessions,
        latest_completed_krx=latest_krx,
        latest_allowed_kospi_session=latest_kospi_live,
    )
    row = {
        "source_id": source_id,
        "provider": selected["provider"].iloc[0] if not selected.empty and "provider" in selected else contract.provider,
        "provider_series_id": selected["provider_series_id"].iloc[0] if not selected.empty and "provider_series_id" in selected else contract.provider_series_id,
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
        "allowed_partial_row_count": date_audit.get("allowed_partial_row_count", 0),
        "excluded_partial_row_count": date_audit.get("excluded_partial_row_count", 0),
        "kospi_partial_daily_allowed": date_audit.get("kospi_partial_daily_allowed", False),
        "kospi_latest_row_final": date_audit.get("kospi_latest_row_final"),
        "kospi_live_observation_type": date_audit.get("kospi_live_observation_type", ""),
        "selected_route": selected["source_route"].iloc[0] if not selected.empty and "source_route" in selected else "",
        "selected_attempt": retry_meta["selected_attempt"],
        "row_count": int(len(selected.loc[selected.get("valid", False).astype(bool)])) if not selected.empty else 0,
    }
    return selected, row


def _latest_valid_source_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame is None or frame.empty or "valid" not in frame or "observation_date" not in frame:
        return None
    valid = frame.loc[frame["valid"].astype(bool)]
    if valid.empty:
        return None
    dates = pd.to_datetime(valid["observation_date"], errors="coerce").dropna()
    return None if dates.empty else pd.Timestamp(dates.max()).normalize()


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
        "source_bottleneck_actual_date",
        "confirmed_basis_source_id",
        "confirmed_basis_actual_date",
        "confirmed_basis_expected_date",
        "confirmed_basis_lag_sessions",
        "blocked_source_ids",
    ]
    available = [col for col in columns if col in candidate_freshness.columns]
    rows = candidate_freshness[available].to_dict("records")
    for row in rows:
        provisional = pd.to_datetime(row.get("basis_date"), errors="coerce")
        confirmed = pd.to_datetime(
            row.get("confirmed_basis_actual_date") or row.get("source_bottleneck_actual_date"),
            errors="coerce",
        )
        row["provisional_basis_date"] = None if pd.isna(provisional) else provisional.strftime("%Y-%m-%d")
        row["confirmed_basis_date"] = (
            row["provisional_basis_date"]
            if pd.isna(confirmed) or (not pd.isna(provisional) and confirmed > provisional)
            else confirmed.strftime("%Y-%m-%d")
        )
        row["availability_status"] = "CONFIRMED" if row["confirmed_basis_date"] == row["provisional_basis_date"] else "PROVISIONAL"
    return rows


def _role_aware_outputs(
    candidate_freshness: pd.DataFrame,
    candidate_history: pd.DataFrame,
    operating_dictionary: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]], pd.DataFrame]:
    history = candidate_history.copy()
    history["date"] = pd.to_datetime(history["date"]).dt.normalize()
    history = history.sort_values(["candidate_id", "date"], kind="mergesort").reset_index(drop=True)
    t1_position = pd.to_numeric(history["t1_position"], errors="coerce")
    history["raw_risk_state"] = (1 - t1_position).astype("Int8")
    t1_valid = history["t1_valid"].fillna(t1_position.notna()) if "t1_valid" in history else t1_position.notna()
    history["valid_signal"] = history["valid_signal"].fillna(False).astype(bool) & t1_valid.fillna(False).astype(bool) & t1_position.notna()
    on_count = pd.to_numeric(history.get("on_count"), errors="coerce") if "on_count" in history else pd.Series(pd.NA, index=history.index, dtype="Float64")
    active_count = pd.to_numeric(history.get("active_count"), errors="coerce") if "active_count" in history else pd.Series(pd.NA, index=history.index, dtype="Float64")
    count_source = on_count.combine_first(active_count)
    history["active_count"] = count_source.groupby(history["candidate_id"], sort=False).shift(1).astype("Int16")
    previous = history.groupby("candidate_id", sort=False)["raw_risk_state"].shift(1)
    valid = history["valid_signal"]
    history["risk_start_signal"] = (valid & history["raw_risk_state"].eq(1) & previous.ne(1)).fillna(False).astype("int8")
    history["risk_end_signal"] = (valid & history["raw_risk_state"].eq(0) & previous.eq(1)).fillna(False).astype("int8")

    snapshot = candidate_freshness.copy()
    t1 = pd.to_numeric(snapshot["t1_position"], errors="coerce")
    snapshot["raw_risk_state"] = (1 - t1).astype("Int64")
    snapshot["t1_valid"] = snapshot.get("t1_valid", t1.notna()).fillna(False).astype(bool) & t1.notna()
    snapshot["valid_signal"] = snapshot.get("valid_signal", snapshot["calculable"]).fillna(False).astype(bool) & snapshot["t1_valid"]
    snapshot["status"] = snapshot.apply(
        lambda row: "USABLE" if bool(row.get("calculable")) and bool(row.get("freshness_qualified")) and bool(row.get("t1_valid")) else "UNAVAILABLE",
        axis=1,
    )
    if "availability_status" not in snapshot:
        snapshot["availability_status"] = "CONFIRMED"
    for column in ("week_ago_raw_risk_state", "week_ago_basis_date"):
        if column not in snapshot:
            snapshot[column] = pd.NA
    for idx, row in snapshot.iterrows():
        current = candidate_history_rows_at_offsets(
            history,
            row["candidate_id"],
            row.get("basis_date"),
            offsets=(0,),
            valid_col="valid_signal",
        )[0]
        if current is not None:
            snapshot.at[idx, "active_count"] = current.get("active_count")
            snapshot.at[idx, "official_state_date"] = current.get("date")
        selected = candidate_history_rows_at_offsets(
            history,
            row["candidate_id"],
            row.get("basis_date"),
            offsets=(5,),
            valid_col="valid_signal",
        )[5]
        if selected is not None:
            snapshot.at[idx, "week_ago_raw_risk_state"] = selected.get("raw_risk_state")
            snapshot.at[idx, "week_ago_basis_date"] = selected.get("date")

    document = load_role_metadata()
    final = pd.DataFrame(
        [
            {
                "candidate_id": row["candidate_id"],
                "model_family": str(row["model_type"]).upper(),
            }
            for row in operating_dictionary["candidates"]
        ]
    )
    role_outputs = compute_role_aware_market_outputs(
        "KOSPI",
        final,
        snapshot,
        history,
        metadata_document=document,
    )

    metadata = document["markets"]["KOSPI"]
    individual_rows: list[dict[str, Any]] = []
    for candidate in operating_dictionary["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        candidate_snapshot = snapshot.loc[snapshot["candidate_id"].astype(str).eq(candidate_id)]
        if candidate_snapshot.empty:
            continue
        snap = candidate_snapshot.iloc[0]
        combo = str(candidate["model_type"]).upper()
        designation = next(
            record["designation"]
            for record in metadata[combo]
            if str(record["candidate_id"]) == candidate_id
        )
        for offset, timepoint_code, label in TIMEPOINTS:
            if offset == 0:
                selected = snap
            else:
                selected = candidate_history_rows_at_offsets(
                    history,
                    candidate_id,
                    snap.get("basis_date"),
                    offsets=(offset,),
                    valid_col="valid_signal",
                )[offset]
            state = None if selected is None else selected.get("raw_risk_state")
            date = None if selected is None else selected.get("date", snap.get("basis_date"))
            count = None if selected is None else selected.get("active_count")
            try:
                state = None if pd.isna(state) else int(state)
            except (TypeError, ValueError):
                state = None
            try:
                count = None if pd.isna(count) else int(count)
            except (TypeError, ValueError):
                count = None
            individual_rows.append(
                {
                    "market": "KOSPI",
                    "combo": combo,
                    "candidate_id": candidate_id,
                    "designation": designation,
                    "role_1": next(record["role_1"] for record in metadata[combo] if str(record["candidate_id"]) == candidate_id),
                    "role_2": next((record.get("role_2", "") for record in metadata[combo] if str(record["candidate_id"]) == candidate_id), ""),
                    "E_M_H": classify_role_combo(
                        next(record["role_1"] for record in metadata[combo] if str(record["candidate_id"]) == candidate_id),
                        next((record.get("role_2") for record in metadata[combo] if str(record["candidate_id"]) == candidate_id), None),
                    ).warning_class,
                    "timepoint_code": timepoint_code,
                    "timepoint": label,
                    "offset_trading_days": offset,
                    "evaluation_date": "" if date is None or pd.isna(date) else pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "signal": "UNAVAILABLE" if state is None else ("Risk-off" if state else "Risk-on"),
                    "official_t1_risk_off": state,
                    "active_count_official_t1": count,
                    "N_or_M": int(candidate["N_or_M"]),
                    "K": int(candidate["K"]),
                    "L": int(candidate["L"]),
                    "state_status": "PASS" if state in (0, 1) else "UNAVAILABLE",
                }
            )
    individual = pd.DataFrame(individual_rows)

    h_class: dict[str, set[str]] = {}
    for family in ("COMBO1", "COMBO2"):
        h_class[family] = {
            str(record["candidate_id"])
            for record in metadata[family]
            if str(record["designation"]).upper() == "CONFIRM"
            and classify_role_combo(record.get("role_1"), record.get("role_2")).warning_class == "H"
        }
    red_rows: list[dict[str, Any]] = []
    states_by_time = {
        (str(row["candidate_id"]), str(row["timepoint_code"])): row["official_t1_risk_off"]
        for row in individual.to_dict("records")
    }
    for output in role_outputs:
        if output["combination"] not in {"COMBO1", "COMBO2"}:
            continue
        family = output["combination"]
        records = metadata[family]
        main_id = next(str(record["candidate_id"]) for record in records if record["designation"] == "MAIN")
        confirm_h_off = sum(
            states_by_time.get((candidate_id, output["timepoint_code"])) == 1
            for candidate_id in h_class[family]
        )
        risk_off_count = int(output["risk_off_count"])
        model_count = int(output["model_count"])
        main_off = states_by_time.get((main_id, output["timepoint_code"])) == 1
        red = output["stage_code"] == "SELL"
        all_off = risk_off_count == model_count
        violation = bool(red and not all_off and not (main_off and risk_off_count / model_count >= 0.75 and confirm_h_off >= 1))
        red_rows.append(
            {
                "combo": family,
                "timepoint_code": output["timepoint_code"],
                "stage_code": output["stage_code"],
                "risk_off_count": risk_off_count,
                "model_count": model_count,
                "main_off": int(main_off),
                "confirm_h_off": int(confirm_h_off),
                "all_off_exception": int(all_off),
                "red_contract_violation": int(violation),
                "status": "PASS" if not violation else "FAIL",
            }
        )
    return history, snapshot, individual, role_outputs, pd.DataFrame(red_rows)


def _candidate_signal_history(
    ctx: D1C1Context,
    final9_live: pd.DataFrame,
    candidate_metrics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frozen = _read_asset_frame(ctx, "kospi_final9_reference_signals.parquet")
    if "valid_signal" not in frozen.columns:
        frozen["valid_signal"] = True
    else:
        frozen["valid_signal"] = frozen["valid_signal"].fillna(True).astype(bool)
    metrics = candidate_metrics
    if metrics is None:
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
            "t1_valid",
            "active_count",
        ]
    ].copy()
    return _append_live_tail_and_new(frozen, live, ["candidate_id", "date"], "candidate_id")


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


def _component_signal_history(
    ctx: D1C1Context,
    live: dict[str, pd.DataFrame],
    operating_dictionary: dict[str, Any] | None = None,
    candidate_metrics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frozen = _read_asset_frame(ctx, "kospi_final9_component_reference_signals.parquet")
    if "valid_signal" not in frozen.columns:
        frozen["valid_signal"] = True
    else:
        frozen["valid_signal"] = frozen["valid_signal"].fillna(True).astype(bool)
    final9 = operating_dictionary
    if final9 is None:
        final9 = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    elif "candidates" in final9:
        final9 = {
            str(candidate["candidate_id"]): candidate
            for candidate in final9["candidates"]
        }
    metrics = candidate_metrics
    if metrics is None:
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
                    "component_active_count": source.get("active_count", pd.Series(pd.NA, index=source.index)),
                    "component_risk_start_signal": source.get("risk_start_signal", pd.Series(pd.NA, index=source.index)),
                    "component_risk_end_signal": source.get("risk_end_signal", pd.Series(pd.NA, index=source.index)),
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
    return _append_live_tail_and_new(
        frozen,
        live_components,
        ["parent_candidate_id", "component_id", "date"],
        "parent_candidate_id",
    )


def _benchmark_close_history(transformed: pd.DataFrame) -> pd.DataFrame:
    out = transformed[["date", "kospi_close"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.drop_duplicates(["date"], keep="first").sort_values("date").reset_index(drop=True)


def _transformed_source_history(transformed: pd.DataFrame) -> pd.DataFrame:
    out = transformed.copy()
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.drop_duplicates(["date"], keep="last").sort_values("date").reset_index(drop=True)


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


def _append_live_tail_and_new(
    frozen: pd.DataFrame,
    live: pd.DataFrame,
    key_cols: list[str],
    identity_col: str,
) -> pd.DataFrame:
    frozen = frozen.copy()
    live = live.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    live["date"] = pd.to_datetime(live["date"]).dt.normalize()
    cutoff = frozen["date"].max()
    frozen_ids = set(frozen[identity_col].astype(str))
    old_tail = live.loc[live[identity_col].astype(str).isin(frozen_ids) & live["date"].gt(cutoff)]
    new_history = live.loc[~live[identity_col].astype(str).isin(frozen_ids)]
    additions = pd.concat([old_tail, new_history], ignore_index=True, sort=False)
    if additions.empty:
        return frozen.sort_values(key_cols).drop_duplicates(key_cols, keep="first").reset_index(drop=True)
    columns = list(dict.fromkeys([*frozen.columns.tolist(), *additions.columns.tolist()]))
    combined = pd.concat([frozen.reindex(columns=columns), additions.reindex(columns=columns)], ignore_index=True, sort=False)
    return combined.sort_values(key_cols).drop_duplicates(key_cols, keep="first").reset_index(drop=True)


def _component_template(meta: pd.DataFrame, parent_id: str, component_id: str) -> dict[str, Any]:
    try:
        row = meta.loc[(parent_id, component_id)]
        return row.to_dict()
    except KeyError:
        return {}
