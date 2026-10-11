"""Small presentation helpers for adding historical dashboard timepoints."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

import pandas as pd


TIMEPOINT_OFFSETS = (21, 10, 5, 0)


def timepoint_date_key(value: object) -> str | None:
    date = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(date) else pd.Timestamp(date).strftime("%Y-%m-%d")


def timepoint_header_html(label: str, dates: Iterable[object]) -> str:
    """Render a grouped timepoint heading with its shared or varying date."""
    formatted = sorted({date for value in dates if (date := timepoint_date_key(value)) is not None})
    if len(formatted) == 1:
        date_label = formatted[0]
    elif formatted:
        date_label = "기준일 상이"
    else:
        date_label = "기준일 없음"
    title = f" title='{escape(', '.join(formatted))}'" if len(formatted) > 1 else ""
    return (
        f"{escape(label)}<br>"
        f"<span{title} style='font-size:9px;font-weight:400;color:var(--secondary-text-color,#8F8F8F)'>{escape(date_label)}</span>"
    )


def timepoint_cell_date_html(value: object) -> str:
    """Keep an exceptional candidate-specific date visible when a group varies."""
    label = timepoint_date_key(value)
    if label is None:
        return ""
    return f"<span style='color:var(--secondary-text-color,#8F8F8F);font-size:9px'>{escape(label)}</span><br>"


def history_rows_at_offsets(
    history: pd.DataFrame | None,
    reference_date: object,
    *,
    offsets: Iterable[int] = TIMEPOINT_OFFSETS,
    date_col: str = "date",
    valid_col: str | None = None,
) -> dict[int, pd.Series | None]:
    """Select exact trading-row offsets at or before a candidate's basis date."""
    requested = tuple(dict.fromkeys(max(0, int(offset)) for offset in offsets))
    selected: dict[int, pd.Series | None] = {offset: None for offset in requested}
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or date_col not in history:
        return selected
    basis = pd.to_datetime(reference_date, errors="coerce")
    if pd.isna(basis):
        return selected
    basis = pd.Timestamp(basis)
    basis = basis.tz_convert(None) if basis.tzinfo is not None else basis
    basis = basis.normalize()

    rows = history.copy()
    dates = pd.to_datetime(rows[date_col], errors="coerce")
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    rows[date_col] = dates.dt.normalize()
    rows = rows.dropna(subset=[date_col]).loc[lambda frame: frame[date_col].le(basis)]
    validity_column = None
    if valid_col is not None:
        validity_column = valid_col if valid_col in rows else ("valid" if valid_col == "valid_signal" and "valid" in rows else None)
    if validity_column is not None:
        valid = rows[validity_column].map(_truthy_valid)
        rows = rows.loc[valid]
    rows = rows.sort_values(date_col, kind="mergesort").drop_duplicates(date_col, keep="last").reset_index(drop=True)
    for offset in requested:
        if len(rows) > offset:
            selected[offset] = rows.iloc[-offset - 1].copy()
    return selected


def candidate_history_rows_at_offsets(
    history: pd.DataFrame | None,
    candidate_id: object,
    reference_date: object,
    *,
    offsets: Iterable[int] = TIMEPOINT_OFFSETS,
    candidate_col: str = "candidate_id",
    date_col: str = "date",
    valid_col: str | None = None,
) -> dict[int, pd.Series | None]:
    """Apply the offset selector to one candidate without changing its basis."""
    requested = tuple(offsets)
    empty = {max(0, int(offset)): None for offset in requested}
    if history is None or not isinstance(history, pd.DataFrame) or candidate_col not in history:
        return empty
    rows = history.loc[history[candidate_col].astype(str).eq(str(candidate_id))]
    return history_rows_at_offsets(
        rows,
        reference_date,
        offsets=requested,
        date_col=date_col,
        valid_col=valid_col,
    )


def candidate_signal_position_rows_at_offsets(
    history: pd.DataFrame | None,
    candidate_id: object,
    reference_date: object,
    *,
    signal_state_col: str,
    position_state_col: str,
    offsets: Iterable[int] = TIMEPOINT_OFFSETS,
    candidate_col: str = "candidate_id",
    date_col: str = "date",
    valid_col: str | None = None,
    signal_lag_sessions: int = 1,
) -> dict[int, dict[str, object]]:
    """Pair each application row with the source-exact signal history row.

    This is presentation-only: the application row's official T+1 state is
    never shifted or recomputed. ``signal_lag_sessions`` follows the existing
    market/strategy history contract: 1 for raw signal histories whose T+1
    position is stored on the next row, 0 when component T+1 has already been
    applied before candidate aggregation. A pair is aligned only on an exact
    binary-state match.
    """
    if signal_lag_sessions < 0:
        raise ValueError("signal_lag_sessions must be non-negative")
    selected = candidate_history_rows_at_offsets(
        history,
        candidate_id,
        reference_date,
        offsets=offsets,
        candidate_col=candidate_col,
        date_col=date_col,
        valid_col=valid_col,
    )
    empty = {
        offset: {"application_row": None, "signal_row": None, "aligned": False, "reason": "NO_APPLICATION_ROW"}
        for offset in selected
    }
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return empty
    if not {candidate_col, date_col, signal_state_col, position_state_col}.issubset(history.columns):
        return {
            offset: {"application_row": row, "signal_row": None, "aligned": False, "reason": "MISSING_STATE_COLUMN"}
            for offset, row in selected.items()
        }

    rows = history.loc[history[candidate_col].astype(str).eq(str(candidate_id))].copy()
    dates = pd.to_datetime(rows[date_col], errors="coerce")
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    rows[date_col] = dates.dt.normalize()
    rows = rows.dropna(subset=[date_col]).sort_values(date_col, kind="mergesort")
    rows = rows.drop_duplicates(date_col, keep="last").reset_index(drop=True)

    paired: dict[int, dict[str, object]] = {}
    for offset, application in selected.items():
        if application is None:
            paired[offset] = empty[offset]
            continue
        application_date = pd.to_datetime(application.get(date_col), errors="coerce")
        if pd.isna(application_date):
            paired[offset] = {"application_row": application, "signal_row": None, "aligned": False, "reason": "INVALID_APPLICATION_DATE"}
            continue
        application_date = pd.Timestamp(application_date).normalize()
        application_positions = rows.index[rows[date_col].eq(application_date)].tolist()
        if not application_positions:
            paired[offset] = {"application_row": application, "signal_row": None, "aligned": False, "reason": "APPLICATION_ROW_NOT_IN_HISTORY"}
            continue
        signal_position = application_positions[-1] - signal_lag_sessions
        if signal_position < 0:
            paired[offset] = {"application_row": application, "signal_row": None, "aligned": False, "reason": "NO_SOURCE_SIGNAL_ROW"}
            continue
        signal = rows.iloc[signal_position].copy()
        if valid_col and valid_col in signal and not _truthy_valid(signal[valid_col]):
            paired[offset] = {"application_row": application, "signal_row": signal, "aligned": False, "reason": "PRIOR_SIGNAL_INVALID"}
            continue
        signal_state = _binary_state(signal.get(signal_state_col))
        applied_state = _binary_state(application.get(position_state_col))
        aligned = signal_state is not None and applied_state is not None and signal_state == applied_state
        paired[offset] = {
            "application_row": application,
            "signal_row": signal,
            "aligned": aligned,
            "reason": "PASS" if aligned else "OFFICIAL_T1_MISMATCH_OR_MISSING",
        }
    return paired


def risk_state_short_label(value: object) -> str:
    """Render only an authoritative binary state; never infer it from stage text."""
    try:
        if pd.isna(value):
            return "R-계산 불가"
        state = int(value)
    except (TypeError, ValueError, OverflowError):
        return "R-계산 불가"
    if state not in (0, 1):
        return "R-계산 불가"
    return "R-off" if state == 1 else "R-on"


def _truthy_valid(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _binary_state(value: object) -> int | None:
    try:
        if pd.isna(value):
            return None
        state = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return state if state in (0, 1) else None
