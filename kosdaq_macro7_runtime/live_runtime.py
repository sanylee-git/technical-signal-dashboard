"""Independent, Frozen-prefix-preserving Macro7 Live runtime."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from .frozen_replay import _candidate_frame, _combine, _final_t1, _metrics, _performance
from .live_sources import SOURCE_SPECS, fetch_all_sources
from .market_calendar import latest_allowed_live_session, latest_completed_session, load_calendar, session_status, sessions_between


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "kosdaq_macro7_assets"
FROZEN_CUTOFF = pd.Timestamp("2026-07-28")
EVALUATION_START = "2008-04-01"

FAMILY_SOURCES = {
    "kosdaq_index_level": ("kosdaq_ohlcv",), "kosdaq_bollinger": ("kosdaq_ohlcv",),
    "kosdaq_hv": ("kosdaq_ohlcv",), "kosdaq_natr": ("kosdaq_ohlcv",), "kosdaq_rsi": ("kosdaq_ohlcv",),
    "usdkrw_level": ("usdkrw",), "vix_level": ("vix",), "vix_spread": ("vix", "vix3m"),
    "us_10y_real_yield_level": ("us_10y_real_yield",), "us_10y_2y_spread": ("us_10y_yield", "us_2y_yield"),
    "us_10y_3m_spread": ("us_10y_yield", "us_3m_yield"), "us_10y_slope": ("us_10y_yield",),
    "us_hy_oas_level": ("us_baa_corp_yield", "us_10y_yield"), "us_ig_oas_level": ("us_aaa_corp_yield", "us_10y_yield"),
    "global_credit_stress": ("us_baa_corp_yield", "us_10y_yield", "nfci", "vix"),
}


def _as_utc(as_of: datetime | pd.Timestamp | None) -> pd.Timestamp:
    value = pd.Timestamp(as_of or datetime.now(timezone.utc))
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def _date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def normalize_daily_merge_key(series: pd.Series) -> pd.Series:
    """Return timezone-naive daily merge keys with a stable pandas dtype."""

    converted = pd.to_datetime(series, errors="coerce")
    if converted.dt.tz is not None:
        converted = converted.dt.tz_localize(None)
    return converted.dt.normalize().astype("datetime64[ns]")


def _load_frozen() -> pd.DataFrame:
    frame = pd.read_parquet(ASSETS / "frozen/frozen_kosdaq_macro_snapshot.parquet").copy()
    frame["date"] = normalize_daily_merge_key(frame["date"])
    return frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "valid" not in frame:
        return frame.iloc[0:0].copy()
    out = frame.loc[frame["valid"].astype(bool)].copy()
    out["observation_date"] = normalize_daily_merge_key(out["observation_date"])
    return out.dropna(subset=["observation_date"]).sort_values("observation_date")


def _source_availability(frame: pd.DataFrame, source_id: str, dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    spec = SOURCE_SPECS[source_id]
    valid = _valid(frame)
    if valid.empty:
        empty = pd.DataFrame({"date": dates, source_id: np.nan, f"{source_id}_observation_date": pd.NaT, f"{source_id}_available_date": pd.NaT})
        return empty, {"source_id": source_id, "observation_date": None, "available_through_date": None, "freshness_status": "FETCH_ERROR", "reason": "no valid provider rows"}
    valid = valid[["observation_date", "value"]].copy()
    valid["available_date"] = normalize_daily_merge_key(valid["observation_date"] + BDay(spec.lag_bdays))
    # Provider revisions may include old observations. They may seed a new post-cutoff availability date,
    # but never overwrite the Frozen prefix.
    available = valid.loc[valid["available_date"].gt(FROZEN_CUTOFF)].sort_values("available_date")
    target = pd.DataFrame({"date": normalize_daily_merge_key(pd.Series(dates)).to_numpy()}).sort_values("date")
    merged = pd.merge_asof(target, available, left_on="date", right_on="available_date", direction="backward")
    merged = merged.rename(columns={"value": source_id, "observation_date": f"{source_id}_observation_date", "available_date": f"{source_id}_available_date"})
    actual_observation = valid["observation_date"].max()
    actual_available = valid["available_date"].max()
    last_used = merged.loc[merged[source_id].notna(), "date"].max() if merged[source_id].notna().any() else pd.NaT
    sessions_at_raw_availability = dates[dates <= actual_available] if not pd.isna(actual_available) else pd.DatetimeIndex([])
    return merged, {"source_id": source_id, "observation_date": _date(actual_observation), "available_through_date": _date(last_used), "last_observable_session": _date(sessions_at_raw_availability.max() if len(sessions_at_raw_availability) else pd.NaT), "raw_available_date": _date(actual_available), "freshness_status": "PENDING", "reason": ""}


def _freshness(source_id: str, info: dict[str, Any], latest_session: pd.Timestamp | None, as_of: pd.Timestamp) -> dict[str, Any]:
    spec = SOURCE_SPECS[source_id]
    if latest_session is None or info["observation_date"] is None:
        return {**info, "freshness_status": "FETCH_ERROR", "expected_observation_date": None}
    latest = pd.Timestamp(latest_session)
    actual = pd.Timestamp(info["observation_date"])
    if source_id == "kosdaq_ohlcv":
        status = "FRESH" if actual >= latest else "STALE"
        expected = latest
    elif source_id == "nfci":
        release = (actual + BDay(3)).normalize()
        next_release = (release + BDay(5)).normalize()
        now_date = as_of.tz_convert("UTC").tz_localize(None).normalize()
        status = "NO_NEW_RELEASE_EXPECTED" if now_date < next_release else ("EXPECTED_CADENCE_LAG" if now_date <= next_release + BDay(1) else "STALE")
        expected = None
    else:
        expected = (latest - BDay(spec.lag_bdays)).normalize()
        status = "FRESH" if actual >= expected else "STALE"
    if status == "STALE":
        info = {**info, "available_through_date": info.get("last_observable_session")}
    return {**info, "freshness_status": status, "expected_observation_date": _date(expected)}


def _market_tail(
    frame: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    latest_session: pd.Timestamp | None,
    *,
    session_is_intraday: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    valid = _valid(frame)
    if latest_session is None:
        return valid.iloc[0:0].copy(), {"last_market_row_date": None, "last_market_row_status": "INVALID", "last_valid_close_date": None, "last_valid_close_value": None}
    session_set = set(sessions)
    valid = valid.loc[valid["observation_date"].isin(session_set)].copy()
    tail = valid.loc[valid["observation_date"].gt(FROZEN_CUTOFF) & valid["observation_date"].le(latest_session)].copy()
    tail["row_status"] = "FINAL"
    if session_is_intraday:
        tail.loc[tail["observation_date"].eq(latest_session), "row_status"] = "INTRADAY"
    last = tail.sort_values("observation_date").tail(1)
    return tail, {
        "last_market_row_date": _date(valid["observation_date"].max() if not valid.empty else pd.NaT),
        "last_market_row_status": str(last["row_status"].iloc[0]) if not last.empty else "INVALID",
        "last_valid_close_date": _date(last["observation_date"].iloc[0] if not last.empty else pd.NaT),
        "last_valid_close_value": None if last.empty else float(last["close"].iloc[0]),
    }


def _rolling_zscore(series: pd.Series, window: int = 252) -> pd.Series:
    mean = series.rolling(window, min_periods=max(30, window // 4)).mean()
    std = series.rolling(window, min_periods=max(30, window // 4)).std().replace(0.0, np.nan)
    return ((series - mean) / std).clip(-3.0, 3.0)


def _combined_frame(frozen: pd.DataFrame, frames: dict[str, pd.DataFrame], as_of: pd.Timestamp) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    calendar_asset = load_calendar()
    completed_session = latest_completed_session(as_of, calendar_asset)
    latest_session = latest_allowed_live_session(as_of, calendar_asset)
    session_is_intraday = session_status(as_of, calendar_asset) == "INTRADAY"
    available_sessions = sessions_between(FROZEN_CUTOFF + pd.Timedelta(days=1), latest_session, calendar_asset) if latest_session is not None else pd.DatetimeIndex([])
    market, market_meta = _market_tail(
        frames["kosdaq_ohlcv"],
        available_sessions,
        latest_session,
        session_is_intraday=session_is_intraday,
    )
    tail_dates = pd.DatetimeIndex(pd.to_datetime(market["observation_date"])).normalize().sort_values().unique() if not market.empty else pd.DatetimeIndex([])
    out = frozen.copy()
    if len(tail_dates):
        tail = pd.DataFrame({"date": tail_dates})
        for column in frozen.columns:
            if column != "date":
                tail[column] = np.nan
        market_by_date = market.set_index("observation_date")
        for raw, target in [("open", "kosdaq_open"), ("high", "kosdaq_high"), ("low", "kosdaq_low"), ("close", "kosdaq_close"), ("volume", "kosdaq_volume")]:
            tail[target] = pd.to_numeric(market_by_date[raw].reindex(tail_dates), errors="coerce").to_numpy()
        tail["kosdaq_performance_price"] = tail["kosdaq_close"]
        tail["kosdaq_performance_calendar_eligible"] = tail["kosdaq_close"].notna() & tail["kosdaq_close"].gt(0)
        tail["kosdaq_ohlc_signal_eligible"] = tail[["kosdaq_open", "kosdaq_high", "kosdaq_low", "kosdaq_close"]].notna().all(axis=1)
        tail["kosdaq_market_data_status"] = market["row_status"].map({"FINAL": "LIVE_FINAL", "INTRADAY": "LIVE_INTRADAY"}).to_numpy()
        out = pd.concat([out, tail], ignore_index=True)
    out = out.sort_values("date").drop_duplicates("date", keep="first").reset_index(drop=True)
    tail_dates = pd.DatetimeIndex(out.loc[out["date"].gt(FROZEN_CUTOFF), "date"]).normalize()
    source_info: list[dict[str, Any]] = []
    for source_id in SOURCE_SPECS:
        if source_id == "kosdaq_ohlcv":
            continue
        aligned, info = _source_availability(frames[source_id], source_id, tail_dates)
        info = _freshness(source_id, info, latest_session, as_of)
        source_info.append(info)
        if len(tail_dates):
            out.loc[out["date"].gt(FROZEN_CUTOFF), source_id] = aligned[source_id].to_numpy()
    if len(tail_dates):
        tail_mask = out["date"].gt(FROZEN_CUTOFF)
        out["hy_proxy"] = out["us_baa_corp_yield"] - out["us_10y_yield"]
        out["ig_proxy"] = out["us_aaa_corp_yield"] - out["us_10y_yield"]
        out["vix_spread"] = out["vix"] - out["vix3m"]
        out["us_10y_2y_spread"] = out["us_10y_yield"] - out["us_2y_yield"]
        out["us_10y_3m_spread"] = out["us_10y_yield"] - out["us_3m_yield"]
        out["usdkrw_safe"] = -out["usdkrw"]
        out["vix_safe"] = -out["vix"]
        out["vix_spread_safe"] = -out["vix_spread"]
        out["real_yield_10y_safe"] = -out["us_10y_real_yield"]
        out["hy_safe"] = -out["hy_proxy"]
        out["ig_safe"] = -out["ig_proxy"]
        parts = pd.concat([_rolling_zscore(out["hy_proxy"]), _rolling_zscore(out["nfci"]), _rolling_zscore(out["vix"])], axis=1)
        out["credit_stress_raw"] = parts.mean(axis=1)
        out["credit_stress_safe"] = -out["credit_stress_raw"]
        raw_columns = ["usdkrw", "vix", "vix3m", "us_10y_real_yield", "us_10y_yield", "us_2y_yield", "us_3m_yield", "us_baa_corp_yield", "us_aaa_corp_yield", "nfci"]
        out.loc[tail_mask, "common_macro_reference_available"] = out.loc[tail_mask, raw_columns].notna().all(axis=1)
        out.loc[tail_mask, "official_operating_model"] = False
        out.loc[tail_mask, "data_contract_version"] = "kosdaq_macro7_live_tail_v1"
    # Frozen rows are authoritative, including availability-adjusted derived values.
    # Live calculations may use the full history for warm-up, but can never rewrite it.
    frozen_indexed = frozen.set_index("date")
    output_index = pd.DatetimeIndex(out["date"])
    for column in frozen.columns:
        if column != "date" and column in out.columns:
            restored = pd.Series(out[column].to_numpy(), index=output_index)
            restored.loc[frozen_indexed.index] = frozen_indexed[column]
            out[column] = restored.reindex(output_index).to_numpy()
    market_info = _freshness("kosdaq_ohlcv", {"source_id": "kosdaq_ohlcv", "observation_date": market_meta["last_valid_close_date"], "available_through_date": market_meta["last_valid_close_date"], "raw_available_date": market_meta["last_valid_close_date"], "reason": ""}, latest_session, as_of)
    source_info.insert(0, market_info)
    merge = {**market_meta, "latest_completed_session": _date(completed_session), "latest_calculation_session": _date(latest_session), "frozen_rows_overwritten": 0, "live_rows_on_or_before_cutoff_used_for_runtime": 0, "duplicate_date_count": int(out["date"].duplicated().sum()), "live_tail_first_date": _date(tail_dates.min() if len(tail_dates) else pd.NaT), "live_tail_last_date": _date(tail_dates.max() if len(tail_dates) else pd.NaT), "live_tail_row_count": int(len(tail_dates))}
    return out, source_info, merge


def _continuous_basis(core: pd.DataFrame, candidate_id: str, source_limit: pd.Timestamp | None) -> tuple[pd.Timestamp | None, str | None]:
    if source_limit is None or source_limit <= FROZEN_CUTOFF:
        return None, "SOURCE_NOT_AVAILABLE_AFTER_FROZEN"
    rows = core.loc[core["candidate_id"].eq(candidate_id)].sort_values("date")
    tail = rows.loc[rows["date"].gt(FROZEN_CUTOFF) & rows["date"].le(source_limit)]
    invalid = tail.loc[~tail["valid_signal"].astype(bool), "date"]
    if not invalid.empty:
        return None, "POST_FROZEN_INVALID_GAP"
    return pd.Timestamp(source_limit), None


def _combine_until(core: pd.DataFrame, combo_id: str, ids: list[str], k: int, l: int, bases: dict[str, pd.Timestamp | None]) -> tuple[pd.DataFrame | None, pd.Timestamp | None, str | None]:
    usable = [bases.get(candidate_id) for candidate_id in ids]
    if any(value is None for value in usable):
        return None, None, "CHILD_OR_COMPONENT_UNAVAILABLE"
    basis = min(pd.Timestamp(value) for value in usable if value is not None)
    if basis < FROZEN_CUTOFF:
        return None, None, "NO_CONTINUOUS_POST_FROZEN_RANGE"
    narrowed = core.loc[core["date"].le(basis)]
    try:
        return _combine(narrowed, combo_id, ids, k, l, EVALUATION_START), basis, None
    except ValueError as exc:
        return None, None, str(exc)


def _segment_snapshot(state: pd.DataFrame, combined: pd.DataFrame, basis: pd.Timestamp) -> dict[str, Any]:
    row = state.loc[state["date"].eq(basis)].iloc[-1]
    same = state.loc[state["date"].le(basis)].copy()
    current = bool(row["raw_risk_state"])
    opposite_positions = np.flatnonzero(same["raw_risk_state"].astype(bool).to_numpy() != current)
    start_index = int(opposite_positions[-1] + 1) if len(opposite_positions) else 0
    start = pd.Timestamp(same.iloc[start_index]["date"])
    segment = combined.loc[combined["date"].between(start, basis), ["date", "kosdaq_close"]].dropna()
    segment_return = None if len(segment) < 2 else float(segment["kosdaq_close"].iloc[-1] / segment["kosdaq_close"].iloc[0] - 1.0)
    week_ago = same.iloc[-6] if len(same) >= 6 else None
    return {"state_date": _date(basis), "valid": True, "raw_risk_state": current, "active_count": int(row["active_count"]), "current_risk_start_date": _date(start), "current_duration_trading_days": int(len(segment)), "current_segment_return": segment_return, "current_segment_return_end_date": _date(basis), "week_ago_state_date": None if week_ago is None else _date(week_ago["date"]), "week_ago_raw_risk_state": None if week_ago is None else bool(week_ago["raw_risk_state"]), "week_ago_active_count": None if week_ago is None else int(week_ago["active_count"]), "week_ago_valid": week_ago is not None}


def run_live_runtime(*, as_of: datetime | pd.Timestamp | None = None, provider_frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    as_of_utc = _as_utc(as_of)
    contract = json.loads((ASSETS / "kosdaq_macro7_live_source_contract.json").read_text(encoding="utf-8"))
    frozen = _load_frozen()
    frames = provider_frames if provider_frames is not None else fetch_all_sources(as_of=as_of_utc)
    combined, source_status, merge = _combined_frame(frozen, frames, as_of_utc)
    definitions = pd.read_csv(ASSETS / "kosdaq_macro7_signal_definitions.csv")
    final = pd.read_csv(ASSETS / "kosdaq_macro7_final10.csv")
    children = pd.read_csv(ASSETS / "kosdaq_macro7_combo2_child_mapping.csv")
    source_bases = {item["source_id"]: pd.Timestamp(item["available_through_date"]) if item.get("available_through_date") else None for item in source_status}
    core_frames: list[pd.DataFrame] = []
    core_bases: dict[str, pd.Timestamp | None] = {}
    core_reasons: dict[str, str | None] = {}
    for row in definitions.itertuples(index=False):
        frame = _candidate_frame(combined.set_index("date"), pd.Series(row._asdict()))
        frame.insert(0, "candidate_id", row.candidate_id)
        frame = frame.reset_index(drop=True)
        family_sources = FAMILY_SOURCES[str(row.indicator_family)]
        limits = [source_bases[source] for source in family_sources]
        limit = min((value for value in limits if value is not None), default=None)
        basis, reason = _continuous_basis(frame, row.candidate_id, limit)
        if basis is not None:
            frame.loc[frame["date"].gt(basis), "valid_signal"] = False
        core_bases[row.candidate_id], core_reasons[row.candidate_id] = basis, reason
        core_frames.append(frame)
    core = pd.concat(core_frames, ignore_index=True)
    child_parts: list[pd.DataFrame] = []
    child_bases: dict[str, pd.Timestamp | None] = {}
    child_reasons: dict[str, str | None] = {}
    for child_id, group in children.groupby("child_combo1_id", sort=True):
        item = group.iloc[0]
        ids = str(item.child_candidate_ids).split("|")
        part, basis, reason = _combine_until(core, child_id, ids, int(item.child_K), int(item.child_L), core_bases)
        child_bases[child_id], child_reasons[child_id] = basis, reason
        if part is not None:
            child_parts.append(part)
    child = pd.concat(child_parts, ignore_index=True) if child_parts else pd.DataFrame()
    combo1_parts: list[pd.DataFrame] = []
    combo1_bases: dict[str, pd.Timestamp | None] = {}
    combo1_reasons: dict[str, str | None] = {}
    for row in final.loc[final.model_family.eq("COMBO1")].itertuples(index=False):
        part, basis, reason = _combine_until(core, row.candidate_id, str(row.candidate_ids).split("|"), int(row.K), int(row.L), core_bases)
        combo1_bases[row.candidate_id], combo1_reasons[row.candidate_id] = basis, reason
        if part is not None:
            combo1_parts.append(part)
    final_combo1 = pd.concat(combo1_parts, ignore_index=True) if combo1_parts else pd.DataFrame()
    child_core = child.rename(columns={"combo_id": "candidate_id", "raw_risk_state": "risk_state", "valid": "valid_signal"})[["candidate_id", "date", "active_count", "risk_state", "valid_signal", "risk_start", "risk_end"]] if not child.empty else pd.DataFrame()
    combo2_parts: list[pd.DataFrame] = []
    combo2_bases: dict[str, pd.Timestamp | None] = {}
    combo2_reasons: dict[str, str | None] = {}
    for row in final.loc[final.model_family.eq("COMBO2")].itertuples(index=False):
        ids = children.loc[children.parent_combo2_id.eq(row.candidate_id)].sort_values("child_order").child_combo1_id.tolist()
        part, basis, reason = _combine_until(child_core, row.candidate_id, ids, int(row.K), int(row.L), child_bases) if not child_core.empty else (None, None, "CHILD_UNAVAILABLE")
        combo2_bases[row.candidate_id], combo2_reasons[row.candidate_id] = basis, reason
        if part is not None:
            combo2_parts.append(part)
    final_combo2 = pd.concat(combo2_parts, ignore_index=True) if combo2_parts else pd.DataFrame()
    all_final = pd.concat([final_combo1, final_combo2], ignore_index=True) if not final_combo1.empty or not final_combo2.empty else pd.DataFrame()
    t1 = pd.concat([_final_t1(group) for _, group in all_final.groupby("combo_id", sort=True)], ignore_index=True) if not all_final.empty else pd.DataFrame()
    bases = {**combo1_bases, **combo2_bases}
    reasons = {**combo1_reasons, **combo2_reasons}
    snapshots: list[dict[str, Any]] = []
    performances: list[pd.DataFrame] = []
    metrics: list[dict[str, Any]] = []
    for row in final.itertuples(index=False):
        basis = bases.get(row.candidate_id)
        if basis is None or t1.empty:
            snapshots.append({"candidate_id": row.candidate_id, "model_family": row.model_family, "slot": int(row.display_slot), "display_label": row.display_role, "basis_date": None, "state_date": None, "valid": False, "status": "UNAVAILABLE", "reason": reasons.get(row.candidate_id), "K": int(row.K), "L": int(row.L)})
            continue
        state = t1.loc[t1.combo_id.eq(row.candidate_id)].copy()
        snapshot = {"candidate_id": row.candidate_id, "model_family": row.model_family, "slot": int(row.display_slot), "display_label": row.display_role, "basis_date": _date(basis), "K": int(row.K), "L": int(row.L), "status": "USABLE", **_segment_snapshot(state, combined, pd.Timestamp(basis))}
        current = state.loc[state.date.eq(pd.Timestamp(basis))].iloc[-1]
        snapshot["risk_off_t1"] = bool(current["risk_off_t1"])
        snapshot["invest_position"] = int(current["invest_position"])
        snapshots.append(snapshot)
        performance = _performance(combined.loc[combined.date.le(basis)].set_index("date"), state, EVALUATION_START, 10.0)
        performance.insert(0, "candidate_id", row.candidate_id)
        performances.append(performance)
        metrics.append({"candidate_id": row.candidate_id, **_metrics(performance)})
    provisional_state = "COMPUTED" if merge["last_market_row_status"] == "INTRADAY" else "NOT_COMPUTED"
    return {"as_of_utc": as_of_utc.isoformat(), "as_of_kst": as_of_utc.tz_convert("Asia/Seoul").isoformat(), "market_session_status": session_status(as_of_utc), "provisional_intraday_model_state": provisional_state, "contract": contract, "combined": combined, "source_status": pd.DataFrame(source_status), "merge": merge, "core": core, "core_bases": core_bases, "core_reasons": core_reasons, "child": child, "child_bases": child_bases, "final_combo1": final_combo1, "final_combo2": final_combo2, "t1": t1, "snapshot": pd.DataFrame(snapshots), "performance": pd.concat(performances, ignore_index=True) if performances else pd.DataFrame(), "metrics": pd.DataFrame(metrics), "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE", "final_t1_application_count": 1, "invalid_component_as_risk_on_count": 0}
