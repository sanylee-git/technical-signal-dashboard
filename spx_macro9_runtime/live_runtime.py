"""Frozen-prefix-preserving S&P Proxy-only live runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .frozen_runtime import _snapshot, run_frozen_runtime
from .live_replay import replay_core
from .live_sources import SOURCE_SPECS, fetch_all_sources


FROZEN_CUTOFF = pd.Timestamp("2026-08-21")


def _utc(value: object) -> pd.Timestamp:
    result = pd.Timestamp(value or datetime.now(timezone.utc))
    return result.tz_localize("UTC") if result.tzinfo is None else result.tz_convert("UTC")


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "valid" not in frame:
        return pd.DataFrame()
    out = frame.loc[frame["valid"].astype(bool)].copy()
    out["observation_date"] = pd.to_datetime(out["observation_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    return out.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date", keep="last")


def _available(frame: pd.DataFrame, dates: pd.DatetimeIndex, lag: int) -> tuple[pd.Series, pd.Series]:
    source = _valid(frame)
    if source.empty:
        return pd.Series(np.nan, index=dates), pd.Series(pd.NaT, index=dates)
    positions = dates.searchsorted(pd.DatetimeIndex(source["observation_date"]), side="right") + max(0, int(lag) - 1)
    keep = positions < len(dates)
    effective = pd.DataFrame({"effective": dates.take(positions[keep]), "observation": source.loc[keep, "observation_date"].to_numpy(), "value": source.loc[keep, "value"].to_numpy()})
    merged = pd.merge_asof(pd.DataFrame({"date": dates}), effective.sort_values("effective"), left_on="date", right_on="effective", direction="backward")
    return pd.Series(pd.to_numeric(merged["value"], errors="coerce").to_numpy(), index=dates), pd.Series(pd.to_datetime(merged["observation"], errors="coerce").to_numpy(), index=dates)


def _proxy_available(corporate: pd.DataFrame, treasury: pd.DataFrame, dates: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    left = _valid(corporate).set_index("observation_date")["value"]
    right = _valid(treasury).set_index("observation_date")["value"]
    raw = pd.concat([left.rename("corporate"), right.rename("treasury")], axis=1, join="inner").dropna()
    source = pd.DataFrame({"observation_date": raw.index, "value": (raw["corporate"] - raw["treasury"]).to_numpy(), "valid": True})
    return _available(source, dates, 1)


def _z252(series: pd.Series) -> pd.Series:
    mean = series.rolling(252, min_periods=63).mean()
    std = series.rolling(252, min_periods=63).std(ddof=1).replace(0.0, np.nan)
    return ((series - mean) / std).clip(-3.0, 3.0)


def _build_tail(frozen: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    market = _valid(frames.get("spx_ohlcv", pd.DataFrame()))
    market = market.loc[market["observation_date"].gt(FROZEN_CUTOFF)].copy()
    dates = pd.DatetimeIndex(market["observation_date"]).sort_values().unique()
    status = []
    latest_market = pd.Timestamp(dates.max()) if len(dates) else pd.NaT
    prior_market = pd.Timestamp(dates[-2]) if len(dates) > 1 else latest_market
    fresh: dict[str, bool] = {}
    for name, spec in SOURCE_SPECS.items():
        valid = _valid(frames.get(name, pd.DataFrame()))
        latest = pd.NaT if valid.empty else pd.Timestamp(valid["observation_date"].max())
        okay = bool(pd.notna(latest)) and (latest >= latest_market - pd.Timedelta(days=12) if name == "nfci" else latest >= prior_market)
        fresh[name] = okay
        status.append({"source_id": name, "provider": spec.provider, "provider_identifier": spec.provider_identifier, "latest_observation_date": None if pd.isna(latest) else latest.strftime("%Y-%m-%d"), "freshness_status": "FRESH" if okay else "STALE_OR_UNAVAILABLE"})
    if not len(dates) or not all(fresh.values()):
        return pd.DataFrame(), status

    calendar = pd.DatetimeIndex(pd.to_datetime(frozen.loc[frozen["performance_calendar_eligible"].astype(bool), "date"])).append(dates).sort_values().unique()
    tail = pd.DataFrame({"date": dates})
    indexed = market.set_index("observation_date")
    for column in ("open", "high", "low", "close"):
        tail[column] = pd.to_numeric(indexed[column].reindex(dates), errors="coerce").to_numpy()
    for source, target in (("equal_weight", "equal_weight_price"), ("vix", "vix"), ("vix3m", "vix3m"), ("dfii10", "real_yield_10y"), ("dgs10", "dgs10"), ("t10y2y", "spread_10y2y"), ("t10y3m", "spread_10y3m"), ("nfci", "nfci")):
        values, stamps = _available(frames[source], calendar, SOURCE_SPECS[source].lag_market_sessions)
        tail[target] = values.reindex(dates).to_numpy()
        tail[f"{target}_source_observation_date"] = stamps.reindex(dates).to_numpy()
    hy, hy_stamp = _proxy_available(frames["dbaa"], frames["dgs10"], calendar)
    ig, ig_stamp = _proxy_available(frames["daaa"], frames["dgs10"], calendar)
    tail["hy_raw_proxy"] = hy.reindex(dates).to_numpy()
    tail["hy_oas_safe"] = -tail["hy_raw_proxy"]
    tail["hy_source_observation_date"] = hy_stamp.reindex(dates).to_numpy()
    tail["ig_raw_proxy"] = ig.reindex(dates).to_numpy()
    tail["ig_oas_safe"] = -tail["ig_raw_proxy"]
    tail["ig_source_observation_date"] = ig_stamp.reindex(dates).to_numpy()
    tail["vix_spread_safe"] = -(tail["vix"] - tail["vix3m"])
    tail["vix_spread_source_date"] = tail[["vix_source_observation_date", "vix3m_source_observation_date"]].apply(pd.to_datetime, errors="coerce").max(axis=1)
    tail["breadth_raw"] = np.log(tail["equal_weight_price"] / tail["close"])
    tail["breadth_source_date"] = pd.to_datetime(tail["equal_weight_price_source_observation_date"], errors="coerce")
    tail["performance_calendar_eligible"] = tail["close"].gt(0)
    tail["ohlc_signal_eligible"] = tail[["open", "high", "low", "close"]].notna().all(axis=1)
    tail["breadth_input_eligible"] = tail["equal_weight_price"].gt(0) & tail["close"].gt(0)
    return tail, status


def _merge(frozen: pd.DataFrame, tail: pd.DataFrame) -> pd.DataFrame:
    if tail.empty:
        return frozen.copy()
    panel = pd.concat([frozen, tail], ignore_index=True, sort=False).sort_values("date", kind="mergesort").drop_duplicates("date", keep="first").reset_index(drop=True)
    tail_mask = panel["date"].gt(FROZEN_CUTOFF)
    panel["global_credit_stress_safe"] = -pd.concat([_z252(panel["hy_raw_proxy"]), _z252(panel["nfci"]), _z252(panel["vix"])], axis=1).mean(axis=1, skipna=False)
    required = ["hy_oas_safe", "ig_oas_safe", "global_credit_stress_safe", "vix", "vix3m", "real_yield_10y", "spread_10y2y", "spread_10y3m", "dgs10"]
    panel.loc[tail_mask, "core15_input_eligible"] = panel.loc[tail_mask, ["ohlc_signal_eligible", "breadth_input_eligible"]].all(axis=1) & panel.loc[tail_mask, required].notna().all(axis=1)
    panel["core15_input_eligible"] = panel["core15_input_eligible"].eq(True)
    panel["spx_performance_return"] = pd.to_numeric(panel["close"], errors="coerce").pct_change()
    for column in frozen.columns:
        if column != "date" and column in panel:
            panel.loc[: len(frozen) - 1, column] = frozen[column].to_numpy()
    return panel


def _next_state(previous: int, active: int, k: int, l: int) -> int:
    return 1 if active >= k else 0 if active <= l else int(previous)


def _append_history(frozen_runtime: dict[str, Any], panel: pd.DataFrame, *, core: dict[str, dict[str, np.ndarray]] | None = None) -> pd.DataFrame:
    history = frozen_runtime["history"].copy()
    tail = panel.loc[panel["date"].gt(FROZEN_CUTOFF) & panel["core15_input_eligible"].eq(True)].copy()
    if tail.empty:
        return history
    core = replay_core(panel, frozen_runtime["registry"]) if core is None else core
    candidates = frozen_runtime["final10"]
    children = frozen_runtime["children"]
    seeds = frozen_runtime["seeds"]
    c1_raw = dict(seeds["c1_raw"])
    c1_active = dict(seeds["c1_active"])
    child_raw = dict(seeds["child_raw"])
    c2_raw = dict(seeds["c2_raw"])
    c2_active = dict(seeds["c2_active"])
    last_strategy = {
        str(candidate_id): int(group.sort_values("date", kind="mergesort").iloc[-1]["strategy_risk_state"])
        for candidate_id, group in history.groupby("candidate_id", sort=False)
    }
    rows: list[dict[str, object]] = []
    tail_positions = {pd.Timestamp(date).normalize(): position for position, date in enumerate(pd.to_datetime(panel["date"]).dt.normalize())}
    for date in pd.to_datetime(tail["date"]).dt.normalize():
        position = tail_positions[pd.Timestamp(date)]
        c1_current: dict[str, tuple[int, int]] = {}
        for item in candidates.loc[candidates["family"].eq("Combo1")].itertuples(index=False):
            cid = str(item.candidate_id)
            ids = str(item.component_ids_key).split("|")
            values = [core[value]["raw"][position] for value in ids]
            valid = [core[value]["valid"][position] and core[value]["raw"][position] >= 0 for value in ids]
            if not all(valid):
                return history
            active = int(np.sum(values))
            state = int(c1_raw[cid])
            rows.append({"candidate_id": cid, "date": date, "strategy_risk_state": state, "previous_strategy_risk_state": last_strategy[cid], "active_count": int(c1_active[cid]), "valid": True})
            last_strategy[cid] = state
            c1_raw[cid] = _next_state(state, active, int(item.K), int(item.L))
            c1_active[cid] = active
            c1_current[cid] = (c1_raw[cid], active)
        for child in children.drop_duplicates("child_canonical_parent_id").itertuples(index=False):
            ids = str(child.child_component_ids_key).split("|")
            values = [core[value]["raw"][position] for value in ids]
            valid = [core[value]["valid"][position] and core[value]["raw"][position] >= 0 for value in ids]
            if not all(valid):
                return history
            child_raw[str(child.child_canonical_parent_id)] = _next_state(child_raw[str(child.child_canonical_parent_id)], int(np.sum(values)), int(child.child_K), int(child.child_L))
        for item in candidates.loc[candidates["family"].eq("Combo2")].itertuples(index=False):
            cid = str(item.candidate_id)
            child = children.loc[children["parent_candidate_id"].eq(cid)].sort_values("child_order", kind="mergesort")
            active = int(sum(child_raw[str(value)] for value in child["child_canonical_parent_id"]))
            state = int(c2_raw[cid])
            rows.append({"candidate_id": cid, "date": date, "strategy_risk_state": state, "previous_strategy_risk_state": last_strategy[cid], "active_count": int(c2_active[cid]), "valid": True})
            last_strategy[cid] = state
            c2_raw[cid] = _next_state(state, active, int(item.K), int(item.L))
            c2_active[cid] = active
    appended = pd.DataFrame(rows)
    history = pd.concat([history, appended], ignore_index=True)
    history["risk_start"] = history["strategy_risk_state"].eq(1) & history["previous_strategy_risk_state"].eq(0)
    history["risk_end"] = history["strategy_risk_state"].eq(0) & history["previous_strategy_risk_state"].eq(1)
    return history.sort_values(["candidate_id", "date"], kind="mergesort").reset_index(drop=True)


def run_live_runtime(*, as_of: object = None, provider_frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    frozen_runtime = run_frozen_runtime()
    frames = provider_frames if provider_frames is not None else fetch_all_sources(as_of=as_of)
    tail, source_status = _build_tail(frozen_runtime["panel"], frames)
    panel = _merge(frozen_runtime["panel"], tail)
    valid_tail = panel.loc[panel["date"].gt(FROZEN_CUTOFF) & panel["core15_input_eligible"].eq(True), "date"]
    basis = FROZEN_CUTOFF if valid_tail.empty else pd.Timestamp(valid_tail.iloc[-1]).normalize()
    panel = panel.loc[pd.to_datetime(panel["date"]).le(basis)].copy()
    core = replay_core(panel, frozen_runtime["registry"])
    history = _append_history(frozen_runtime, panel, core=core)
    status = "LIVE" if basis > FROZEN_CUTOFF else "FROZEN_ONLY"
    snapshot = _snapshot(frozen_runtime["final10"], history, panel, status=status)
    return {
        "runtime_mode": "FROZEN_PREFIX_LIVE_TAIL", "network_access": provider_frames is None, "as_of_utc": _utc(as_of).isoformat(),
        "basis_date": basis.strftime("%Y-%m-%d"), "frozen_cutoff": FROZEN_CUTOFF.strftime("%Y-%m-%d"),
        "proxy_only": True, "direct_oas_used": False, "snapshot": snapshot, "metrics": frozen_runtime["metrics"], "history": history,
        "registry": frozen_runtime["registry"], "final10": frozen_runtime["final10"], "children": frozen_runtime["children"], "core": core,
        "panel": panel, "frozen_panel": frozen_runtime["panel"], "source_status": source_status,
        "live_tail_row_count": int(len(panel.loc[pd.to_datetime(panel["date"]).gt(FROZEN_CUTOFF)])), "frozen_rows_overwritten": 0,
        "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE", "final_t1_application_count": 1,
    }
