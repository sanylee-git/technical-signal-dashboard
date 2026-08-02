from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from pandas.tseries.offsets import BDay

from .freshness_contracts import FreshnessContract, source_freshness_contracts
from .krx_calendar import kospi_latest_completed_session
from .live_contracts import SourceContract
from .nfci_schedule import nfci_freshness_status


OK_FRESHNESS_STATUSES = {"FRESH", "EXPECTED_CADENCE_LAG", "NO_NEW_RELEASE_EXPECTED"}
ERROR_STATUSES = {"FETCH_ERROR", "SCHEMA_ERROR", "INVALID_VALUE", "CONTRACT_UNBOUND", "DATE_REGRESSION"}


@dataclass(frozen=True)
class FreshnessEvaluation:
    source_id: str
    expected_latest_observation_date: str | None
    expected_latest_publication_date: str | None
    expected_latest_available_date: str | None
    expected_latest_krx_aligned_date: str | None
    actual_latest_observation_date: str | None
    actual_latest_publication_date: str | None
    actual_latest_available_date: str | None
    actual_latest_krx_aligned_date: str | None
    lag_calendar_days: int | None
    lag_krx_sessions: int | None
    final_freshness_status: str
    notes: str


def _fmt(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _latest_valid(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame is None or frame.empty or "observation_date" not in frame:
        return None
    valid = frame.loc[frame.get("valid", pd.Series(False, index=frame.index)).astype(bool)].copy()
    if valid.empty:
        return None
    value = pd.to_datetime(valid["observation_date"], errors="coerce").dropna()
    if value.empty:
        return None
    return pd.Timestamp(value.max()).normalize()


def _frame_error_status(frame: pd.DataFrame) -> str | None:
    if frame is None or frame.empty:
        return "FETCH_ERROR"
    status = str(frame.get("status", pd.Series([""])).iloc[0])
    if status == "SCHEMA_ERROR":
        return "SCHEMA_ERROR"
    if status in {"TEMPORARY_FETCH_FAILURE", "CONTRACT_BLOCKED"}:
        return "FETCH_ERROR"
    if "valid" in frame and not frame["valid"].astype(bool).any():
        return "INVALID_VALUE"
    return None


def _business_observation_for_available(available_date: pd.Timestamp, lag_bdays: int) -> pd.Timestamp:
    return (pd.Timestamp(available_date).normalize() - BDay(int(lag_bdays))).normalize()


def _lag_sessions(expected: pd.Timestamp | None, actual: pd.Timestamp | None, krx_sessions: pd.DatetimeIndex) -> int | None:
    if expected is None or actual is None:
        return None
    sessions = pd.DatetimeIndex(krx_sessions).normalize().sort_values()
    if sessions.empty:
        return None
    actual = pd.Timestamp(actual).normalize()
    expected = pd.Timestamp(expected).normalize()
    count = int(((sessions > actual) & (sessions <= expected)).sum())
    return max(0, count)


def evaluate_source_freshness(
    source_contract: SourceContract,
    frame: pd.DataFrame,
    *,
    as_of_utc: datetime | pd.Timestamp,
    krx_sessions: pd.DatetimeIndex,
    latest_completed_krx: pd.Timestamp | None = None,
) -> FreshnessEvaluation:
    freshness_contract = source_freshness_contracts()[source_contract.source_id]
    latest_completed_krx = latest_completed_krx or kospi_latest_completed_session(as_of_utc)
    actual_obs = _latest_valid(frame)
    actual_avail = None
    if actual_obs is not None:
        actual_avail = (actual_obs + BDay(int(source_contract.lag_bdays))).normalize()
        if latest_completed_krx is not None and actual_avail > latest_completed_krx:
            actual_avail = pd.Timestamp(latest_completed_krx).normalize()

    expected_avail = pd.Timestamp(latest_completed_krx).normalize() if latest_completed_krx is not None else None
    expected_obs = None
    if expected_avail is not None:
        if source_contract.source_id == "kospi_ohlcv":
            expected_obs = expected_avail
        elif source_contract.source_id == "nfci":
            expected_obs = None
        else:
            expected_obs = _business_observation_for_available(expected_avail, source_contract.lag_bdays)

    status = _frame_error_status(frame)
    notes = ""
    if status is None:
        if source_contract.source_id == "nfci":
            if actual_obs is None:
                status = "FETCH_ERROR"
            else:
                status, schedule = nfci_freshness_status(actual_obs, as_of_utc)
                notes = (
                    f"nfci_schedule={schedule.get('release_contract_version')};"
                    f"expected_release={schedule.get('expected_release_date')};"
                    f"next_expected_release={schedule.get('next_expected_release_date')}"
                )
        elif expected_obs is None or actual_obs is None:
            status = "CONTRACT_UNBOUND" if expected_obs is None else "FETCH_ERROR"
        elif actual_obs >= expected_obs:
            status = "FRESH"
        else:
            status = "STALE"

    lag_calendar_days = None
    if expected_obs is not None and actual_obs is not None:
        lag_calendar_days = max(0, int((pd.Timestamp(expected_obs) - pd.Timestamp(actual_obs)).days))
    lag_krx_sessions = _lag_sessions(expected_avail, actual_avail, krx_sessions)

    return FreshnessEvaluation(
        source_id=source_contract.source_id,
        expected_latest_observation_date=_fmt(expected_obs),
        expected_latest_publication_date=None,
        expected_latest_available_date=_fmt(expected_avail),
        expected_latest_krx_aligned_date=_fmt(expected_avail),
        actual_latest_observation_date=_fmt(actual_obs),
        actual_latest_publication_date=None,
        actual_latest_available_date=_fmt(actual_avail),
        actual_latest_krx_aligned_date=_fmt(actual_avail),
        lag_calendar_days=lag_calendar_days,
        lag_krx_sessions=lag_krx_sessions,
        final_freshness_status=status,
        notes=notes,
    )


def select_attempt(source_id: str, attempts: list[dict[str, object]]) -> dict[str, object]:
    valid = [a for a in attempts if a.get("latest_observation_date")]
    if not valid:
        chosen = attempts[-1]
        return {**chosen, "selected_reason": "NO_VALID_ATTEMPT"}
    valid = sorted(valid, key=lambda x: (str(x.get("latest_observation_date")), int(x.get("row_count") or 0)), reverse=True)
    chosen = valid[0]
    return {**chosen, "selected_reason": "LATEST_VALID_OBSERVATION_AND_COVERAGE"}


def source_freshness_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    preferred = [
        "source_id", "provider", "provider_series_id", "as_of_utc", "as_of_kst",
        "expected_latest_observation_date", "expected_latest_available_date", "expected_latest_krx_aligned_date",
        "actual_latest_observation_date", "actual_latest_available_date", "actual_latest_krx_aligned_date",
        "lag_calendar_days", "lag_krx_sessions", "initial_freshness_status", "retry_executed",
        "retry_freshness_status", "final_freshness_status", "selected_attempt", "selected_route",
        "date_regression", "used_last_known_good", "consistency_status", "notes",
    ]
    df = pd.DataFrame(rows)
    return df[[c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]]
