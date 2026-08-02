from __future__ import annotations

import pandas as pd


def source_status_rows(
    provider_frames: dict[str, pd.DataFrame],
    frozen: pd.DataFrame,
    latest_available: pd.DataFrame,
) -> pd.DataFrame:
    frozen = frozen.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    rows: list[dict[str, object]] = []
    for source_id, frame in provider_frames.items():
        frame = frame.copy()
        valid = frame.loc[frame.get("valid", pd.Series(dtype=bool)).astype(bool)].copy() if not frame.empty else frame
        latest_obs = pd.to_datetime(valid["observation_date"]).max() if not valid.empty and "observation_date" in valid else pd.NaT
        status = "IMPLEMENTED_FETCH_OK" if not valid.empty else (frame["status"].iloc[0] if not frame.empty and "status" in frame else "TEMPORARY_FETCH_FAILURE")
        latest_avail = None
        match = latest_available.loc[latest_available["source_id"].eq(source_id)]
        if not match.empty:
            latest_avail = match["latest_available_date"].iloc[0]
        frozen_last = frozen["date"].max()
        new_tail = 0
        if not valid.empty:
            new_tail = int((pd.to_datetime(valid["observation_date"]).dt.normalize() > frozen_last).sum())
        rows.append(
            {
                "source_id": source_id,
                "provider": frame["provider"].iloc[0] if not frame.empty and "provider" in frame else "",
                "provider_series_id": frame["provider_series_id"].iloc[0] if not frame.empty and "provider_series_id" in frame else "",
                "fetch_status": status if new_tail else ("IMPLEMENTED_NO_NEW_RELEASE" if status == "IMPLEMENTED_FETCH_OK" else status),
                "selected_route": frame["source_route"].iloc[0] if not frame.empty and "source_route" in frame else "",
                "row_count": int(len(valid)),
                "first_observation_date": _date(valid["observation_date"].min()) if not valid.empty else None,
                "latest_observation_date": _date(latest_obs),
                "latest_available_date": latest_avail,
                "frozen_last_observation_date": _date(frozen_last),
                "new_tail_row_count": new_tail,
                "error_type": frame["error_type"].iloc[0] if not frame.empty and "error_type" in frame else "",
                "error_message": frame["error_message"].iloc[0] if not frame.empty and "error_message" in frame else "",
            }
        )
    return pd.DataFrame(rows)


def revision_diff(provider_frames: dict[str, pd.DataFrame], frozen: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    frozen = frozen.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    mapping = {
        "kospi_ohlcv": ("kospi_close", "close"),
        "usdkrw": ("usdkrw", "value"),
        "vix": ("vix", "value"),
        "vix3m": ("vix3m", "value"),
        "us_10y_real_yield": ("us_10y_real_yield", "value"),
        "us_10y_yield": ("us_10y_yield", "value"),
        "us_2y_yield": ("us_2y_yield", "value"),
        "us_3m_yield": ("us_3m_yield", "value"),
        "us_baa_corp_yield": ("us_baa_corp_yield", "value"),
        "us_aaa_corp_yield": ("us_aaa_corp_yield", "value"),
        "nfci": ("nfci", "value"),
    }
    frozen_indexed = frozen.set_index("date")
    for source_id, (frozen_col, live_col) in mapping.items():
        frame = provider_frames.get(source_id, pd.DataFrame())
        if frame.empty or frozen_col not in frozen_indexed.columns or live_col not in frame.columns:
            continue
        good = frame.loc[frame.get("valid", False).astype(bool)].copy()
        if good.empty:
            continue
        good["observation_date"] = pd.to_datetime(good["observation_date"]).dt.normalize()
        overlap = good.loc[good["observation_date"].isin(frozen_indexed.index)].tail(200).copy()
        for rec in overlap.itertuples(index=False):
            date = rec.observation_date
            live_value = getattr(rec, live_col)
            frozen_value = frozen_indexed.loc[date, frozen_col]
            if isinstance(frozen_value, pd.Series):
                frozen_value = frozen_value.iloc[-1]
            abs_diff = None if pd.isna(frozen_value) or pd.isna(live_value) else float(abs(float(frozen_value) - float(live_value)))
            rel_diff = None if not abs_diff or pd.isna(frozen_value) or float(frozen_value) == 0 else float(abs_diff / abs(float(frozen_value)))
            rows.append(
                {
                    "source_id": source_id,
                    "observation_date": _date(date),
                    "frozen_value": None if pd.isna(frozen_value) else float(frozen_value),
                    "provider_live_value": None if pd.isna(live_value) else float(live_value),
                    "absolute_diff": abs_diff,
                    "relative_diff": rel_diff,
                    "revision_detected": bool(abs_diff is not None and abs_diff > 1e-10),
                    "used_for_calculation": False,
                }
            )
    return pd.DataFrame(rows)


def frozen_overwrite_count(frozen: pd.DataFrame, combined: pd.DataFrame, columns: list[str]) -> int:
    frozen = frozen.copy()
    combined = combined.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    combined["date"] = pd.to_datetime(combined["date"]).dt.normalize()
    cmp = frozen[["date", *columns]].merge(combined[["date", *columns]], on="date", suffixes=("_frozen", "_combined"))
    mismatches = 0
    for col in columns:
        left = cmp[f"{col}_frozen"]
        right = cmp[f"{col}_combined"]
        mismatches += int(((left.isna() != right.isna()) | ((~left.isna()) & (~right.isna()) & (abs(left.astype(float) - right.astype(float)) > 1e-10))).sum())
    return mismatches


def _date(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")
