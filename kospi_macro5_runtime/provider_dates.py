from __future__ import annotations

import pandas as pd

from .live_contracts import SourceContract


def normalize_provider_dates_for_freshness(
    contract: SourceContract,
    frame: pd.DataFrame,
    *,
    expected_latest_observation_date: str | None,
    latest_completed_krx_session: str | None,
    latest_allowed_kospi_session: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if frame is None or frame.empty:
        return frame, {
            "source_id": contract.source_id,
            "raw_latest_observation_date": None,
            "selected_latest_observation_date": None,
            "excluded_future_row_count": 0,
            "excluded_partial_row_count": 0,
            "allowed_partial_row_count": 0,
            "weekend_label_mapped_count": 0,
            "unresolved_provider_date_count": 0,
            "future_date_clipped_to_expected_count": 0,
            "kospi_partial_daily_allowed": False,
            "kospi_latest_row_final": None,
            "kospi_live_observation_type": "",
        }
    out = frame.copy()
    out["provider_raw_date"] = pd.to_datetime(out["observation_date"], errors="coerce").dt.normalize()
    out["canonical_observation_date"] = out["provider_raw_date"]
    raw_latest = out.loc[out.get("valid", False).astype(bool), "provider_raw_date"].max()
    expected = pd.Timestamp(expected_latest_observation_date).normalize() if expected_latest_observation_date else None
    latest_krx = pd.Timestamp(latest_completed_krx_session).normalize() if latest_completed_krx_session else None
    latest_kospi_allowed = pd.Timestamp(latest_allowed_kospi_session).normalize() if latest_allowed_kospi_session else latest_krx
    limit = latest_kospi_allowed if contract.source_id == "kospi_ohlcv" else expected
    valid = out.get("valid", pd.Series(False, index=out.index)).astype(bool)
    future_mask = pd.Series(False, index=out.index)
    weekend_unresolved = pd.Series(False, index=out.index)
    partial_mask = pd.Series(False, index=out.index)
    allowed_partial_mask = pd.Series(False, index=out.index)
    if limit is not None:
        future_mask = valid & (out["canonical_observation_date"] > limit)
    if contract.source_id == "usdkrw":
        weekend_unresolved = valid & out["canonical_observation_date"].dt.weekday.ge(5) & future_mask
    if contract.source_id == "kospi_ohlcv" and latest_krx is not None:
        partial_candidate = valid & (out["canonical_observation_date"] > latest_krx)
        if latest_kospi_allowed is not None:
            allowed_partial_mask = partial_candidate & out["canonical_observation_date"].le(latest_kospi_allowed)
        partial_mask = partial_candidate & ~allowed_partial_mask & ~future_mask
    exclude = future_mask | weekend_unresolved | partial_mask
    selected = out.loc[~exclude].copy()
    selected_latest = selected.loc[selected.get("valid", False).astype(bool), "canonical_observation_date"].max() if not selected.empty else pd.NaT
    kospi_latest_row_final = None
    kospi_live_observation_type = ""
    if contract.source_id == "kospi_ohlcv" and not pd.isna(selected_latest):
        kospi_latest_row_final = bool(latest_krx is not None and pd.Timestamp(selected_latest).normalize() <= latest_krx)
        kospi_live_observation_type = "completed_daily" if kospi_latest_row_final else "intraday_partial"
    audit = {
        "source_id": contract.source_id,
        "provider": contract.provider,
        "provider_series_id": contract.provider_series_id,
        "raw_latest_observation_date": None if pd.isna(raw_latest) else pd.Timestamp(raw_latest).strftime("%Y-%m-%d"),
        "selected_latest_observation_date": None if pd.isna(selected_latest) else pd.Timestamp(selected_latest).strftime("%Y-%m-%d"),
        "excluded_future_row_count": int(future_mask.sum()),
        "excluded_partial_row_count": int(partial_mask.sum()),
        "allowed_partial_row_count": int(allowed_partial_mask.sum()),
        "weekend_label_mapped_count": 0,
        "unresolved_provider_date_count": int(weekend_unresolved.sum()),
        "future_date_clipped_to_expected_count": 0,
        "kospi_partial_daily_allowed": bool(contract.source_id == "kospi_ohlcv"),
        "kospi_latest_row_final": kospi_latest_row_final,
        "kospi_live_observation_type": kospi_live_observation_type,
        "provider_date_status": "PASS" if int(weekend_unresolved.sum()) == 0 else "WEEKEND_LABEL_UNRESOLVED",
    }
    if "provider_raw_date" in selected:
        selected = selected.drop(columns=["provider_raw_date", "canonical_observation_date"], errors="ignore")
    return selected.reset_index(drop=True), audit
