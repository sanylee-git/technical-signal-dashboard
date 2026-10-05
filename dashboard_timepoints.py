"""Small presentation helpers for adding historical dashboard timepoints."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


TIMEPOINT_OFFSETS = (21, 10, 5, 0)


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
