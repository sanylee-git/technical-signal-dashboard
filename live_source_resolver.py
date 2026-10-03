from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay


def exact_date_spread(long_frame: pd.DataFrame, short_frame: pd.DataFrame, source_id: str) -> pd.DataFrame:
    """Build a spread only from legs observed on the same date."""
    left = _valid_observations(long_frame).rename(columns={"value": "long_value"})
    right = _valid_observations(short_frame).rename(columns={"value": "short_value"})
    paired = left.merge(right, on="observation_date", how="inner", validate="one_to_one")
    paired["value"] = pd.to_numeric(paired["long_value"], errors="coerce") - pd.to_numeric(paired["short_value"], errors="coerce")
    paired["valid"] = np.isfinite(pd.to_numeric(paired["value"], errors="coerce").to_numpy(dtype=float))
    paired["source_id"] = source_id
    return paired[["observation_date", "value", "valid", "source_id"]].sort_values("observation_date").reset_index(drop=True)


def resolve_aligned_sources(
    dates: pd.DatetimeIndex,
    candidates: Mapping[str, pd.DataFrame],
    *,
    primary_source: str,
    lag: int,
    calendar_mode: str,
    tolerance: float,
    after_date: object | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Align candidates using the market calendar, then select the newest valid observation."""
    target_dates = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize(None).normalize().astype("datetime64[ns]").sort_values().unique()
    if calendar_mode not in {"us_sessions", "business_day"}:
        raise ValueError(f"Unsupported resolver calendar mode: {calendar_mode}")
    if primary_source not in candidates:
        raise KeyError(f"Primary resolver source missing: {primary_source}")
    aligned = {
        source_id: _align_candidate(frame, source_id, target_dates, lag, calendar_mode, after_date)
        for source_id, frame in candidates.items()
    }
    secondary_sources = [source_id for source_id in aligned if source_id != primary_source]
    if len(secondary_sources) != 1:
        raise ValueError("Resolver currently requires exactly one primary and one secondary source")
    secondary_source = secondary_sources[0]
    primary = aligned[primary_source].set_index("date")
    secondary = aligned[secondary_source].set_index("date")
    output: list[dict[str, object]] = []

    for day in target_dates:
        p = primary.loc[day]
        s = secondary.loc[day]
        p_valid = pd.notna(p["observation_date"]) and pd.notna(p["value"])
        s_valid = pd.notna(s["observation_date"]) and pd.notna(s["value"])
        discrepancy = False
        difference = np.nan
        if p_valid and s_valid:
            p_day = pd.Timestamp(p["observation_date"])
            s_day = pd.Timestamp(s["observation_date"])
            if p_day > s_day:
                selected, reason = p, "PRIMARY_FRESHER"
            elif s_day > p_day:
                selected, reason = s, "SECONDARY_FRESHER"
            else:
                difference = abs(float(p["value"]) - float(s["value"]))
                discrepancy = difference > tolerance
                selected = p
                reason = "SAME_DATE_DISCREPANCY_PRIMARY_USED" if discrepancy else "SAME_DATE_PRIMARY_TIEBREAK"
        elif p_valid:
            selected, reason = p, "PRIMARY_ONLY_VALID"
        elif s_valid:
            selected, reason = s, "SECONDARY_ONLY_VALID"
        else:
            selected, reason = None, "NO_VALID_SOURCE"

        output.append({
            "date": day,
            "value": np.nan if selected is None else float(selected["value"]),
            "observation_date": pd.NaT if selected is None else pd.Timestamp(selected["observation_date"]),
            "selected_source": "" if selected is None else str(selected["source_id"]),
            "selection_reason": reason,
            "discrepancy_flag": bool(discrepancy),
            "absolute_difference": difference,
            "primary_observation_date": p["observation_date"] if p_valid else pd.NaT,
            "primary_value": float(p["value"]) if p_valid else np.nan,
            "primary_valid": bool(p_valid),
            "secondary_observation_date": s["observation_date"] if s_valid else pd.NaT,
            "secondary_value": float(s["value"]) if s_valid else np.nan,
            "secondary_valid": bool(s_valid),
        })

    result = pd.DataFrame(output)
    valid_result = result.loc[result["value"].notna()]
    latest = valid_result.iloc[-1] if not valid_result.empty else None
    alerts = result.loc[result["discrepancy_flag"]]
    status = {
        "primary_source": primary_source,
        "secondary_source": secondary_source,
        "selected_source": "" if latest is None else latest["selected_source"],
        "latest_observation_date": "" if latest is None else pd.Timestamp(latest["observation_date"]).strftime("%Y-%m-%d"),
        "latest_model_use_date": "" if latest is None else pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "latest_value": np.nan if latest is None else float(latest["value"]),
        "selection_reason": "NO_VALID_SOURCE" if latest is None else latest["selection_reason"],
        "discrepancy_count": int(len(alerts)),
        "last_discrepancy_date": "" if alerts.empty else pd.Timestamp(alerts.iloc[-1]["date"]).strftime("%Y-%m-%d"),
        "effective_date": "" if valid_result.empty else pd.Timestamp(valid_result.iloc[-1]["date"]).strftime("%Y-%m-%d"),
        "valid_model_dates": int(len(valid_result)),
        "calendar_mode": calendar_mode,
        "availability_lag": int(lag),
    }
    return result, status


def _valid_observations(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or not {"observation_date", "value"}.issubset(frame.columns):
        return pd.DataFrame(columns=["observation_date", "value"])
    out = frame.copy()
    dates = pd.to_datetime(out["observation_date"], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    out["observation_date"] = dates.dt.normalize().astype("datetime64[ns]")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    valid = out.get("valid", out["value"].notna())
    out = out.loc[pd.Series(valid, index=out.index).fillna(False).astype(bool) & out["observation_date"].notna() & out["value"].notna()]
    return out[["observation_date", "value"]].drop_duplicates("observation_date", keep="last").sort_values("observation_date")


def _align_candidate(
    frame: pd.DataFrame,
    source_id: str,
    dates: pd.DatetimeIndex,
    lag: int,
    calendar_mode: str,
    after_date: object | None,
) -> pd.DataFrame:
    source = _valid_observations(frame)
    target = pd.DataFrame({"date": dates})
    if source.empty or target.empty:
        return pd.DataFrame({"date": dates, "observation_date": pd.NaT, "value": np.nan, "source_id": source_id})

    if calendar_mode == "us_sessions":
        positions = dates.searchsorted(pd.DatetimeIndex(source["observation_date"]), side="right") + max(0, int(lag) - 1)
        valid_positions = positions < len(dates)
        aligned_source = source.loc[valid_positions].copy()
        aligned_source["effective_date"] = dates.take(positions[valid_positions])
    else:
        aligned_source = source.copy()
        aligned_source["effective_date"] = (aligned_source["observation_date"] + BDay(int(lag))).dt.normalize().astype("datetime64[ns]")

    if after_date is not None:
        aligned_source = aligned_source.loc[aligned_source["effective_date"].gt(pd.Timestamp(after_date).normalize())]
    aligned_source = aligned_source.sort_values(["effective_date", "observation_date"]).drop_duplicates("effective_date", keep="last")
    merged = pd.merge_asof(
        target.sort_values("date"),
        aligned_source[["effective_date", "observation_date", "value"]],
        left_on="date", right_on="effective_date", direction="backward",
    )
    merged["source_id"] = source_id
    return merged[["date", "observation_date", "value", "source_id"]]
