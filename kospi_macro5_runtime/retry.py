from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from .freshness import OK_FRESHNESS_STATUSES, evaluate_source_freshness
from .live_contracts import SourceContract


def attempt_record(
    *,
    contract: SourceContract,
    attempt_number: int,
    cache_mode: str,
    frame: pd.DataFrame,
    freshness_status: str,
) -> dict[str, object]:
    valid = frame.loc[frame.get("valid", pd.Series(False, index=frame.index)).astype(bool)].copy() if frame is not None and not frame.empty else pd.DataFrame()
    latest = None
    if not valid.empty and "observation_date" in valid:
        latest = pd.to_datetime(valid["observation_date"], errors="coerce").dropna().max()
    return {
        "source_id": contract.source_id,
        "attempt_number": attempt_number,
        "cache_mode": cache_mode,
        "source_route": frame["source_route"].iloc[0] if frame is not None and not frame.empty and "source_route" in frame else "",
        "row_count": int(len(valid)),
        "latest_observation_date": None if pd.isna(latest) else pd.Timestamp(latest).strftime("%Y-%m-%d"),
        "status": frame["status"].iloc[0] if frame is not None and not frame.empty and "status" in frame else "FETCH_ERROR",
        "freshness_status": freshness_status,
        "error": frame["error_message"].iloc[0] if frame is not None and not frame.empty and "error_message" in frame else "",
    }


def fetch_with_optional_bypass(
    contract: SourceContract,
    *,
    as_of_utc: datetime | pd.Timestamp,
    krx_sessions: pd.DatetimeIndex,
    latest_completed_krx: pd.Timestamp,
    latest_allowed_kospi_session: pd.Timestamp | None = None,
    fetcher: Callable[..., pd.DataFrame],
) -> tuple[pd.DataFrame, list[dict[str, object]], dict[str, object]]:
    first = fetcher(contract, cache_mode="NORMAL", as_of_utc=as_of_utc)
    first_eval = evaluate_source_freshness(
        contract,
        first,
        as_of_utc=as_of_utc,
        krx_sessions=krx_sessions,
        latest_completed_krx=latest_completed_krx,
        latest_allowed_kospi_session=latest_allowed_kospi_session,
    )
    attempts = [attempt_record(contract=contract, attempt_number=1, cache_mode="NORMAL", frame=first, freshness_status=first_eval.final_freshness_status)]
    selected = first
    retry_executed = False
    retry_status = "NOT_EXECUTED"
    selected_attempt = 1
    selected_reason = "INITIAL_ATTEMPT"
    if first_eval.final_freshness_status == "STALE":
        retry_executed = True
        token = f"d1c2a_{contract.source_id}_{pd.Timestamp(as_of_utc).value}"
        second = fetcher(contract, cache_mode="BYPASS", bypass_token=token, as_of_utc=as_of_utc)
        second_eval = evaluate_source_freshness(
            contract,
            second,
            as_of_utc=as_of_utc,
            krx_sessions=krx_sessions,
            latest_completed_krx=latest_completed_krx,
            latest_allowed_kospi_session=latest_allowed_kospi_session,
        )
        retry_status = second_eval.final_freshness_status
        attempts.append(attempt_record(contract=contract, attempt_number=2, cache_mode="BYPASS", frame=second, freshness_status=second_eval.final_freshness_status))
        first_latest = attempts[0]["latest_observation_date"] or ""
        second_latest = attempts[1]["latest_observation_date"] or ""
        if second_latest >= first_latest and (second_eval.final_freshness_status in OK_FRESHNESS_STATUSES or second_latest > first_latest):
            selected = second
            selected_attempt = 2
            selected_reason = "BYPASS_NEWER_OR_FRESH"
        else:
            selected_reason = "BYPASS_OLDER_OR_NOT_BETTER_REJECTED"
    meta = {
        "initial_freshness_status": first_eval.final_freshness_status,
        "retry_executed": retry_executed,
        "retry_freshness_status": retry_status,
        "selected_attempt": selected_attempt,
        "selected_reason": selected_reason,
        "freshness_after_retry": retry_status if retry_executed else first_eval.final_freshness_status,
    }
    return selected, attempts, meta
