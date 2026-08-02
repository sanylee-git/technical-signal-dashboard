from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay


def rolling_zscore(series: pd.Series, window: int = 252) -> pd.Series:
    min_periods = max(30, int(window) // 4)
    mean = series.rolling(int(window), min_periods=min_periods).mean()
    std = series.rolling(int(window), min_periods=min_periods).std()
    return ((series - mean) / std.replace(0.0, np.nan)).clip(-3.0, 3.0)


def availability_frame(series: pd.Series, source_id: str, lag_bdays: int) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(series.index).normalize(),
            source_id: pd.to_numeric(series, errors="coerce").to_numpy(dtype=float),
        }
    ).dropna(subset=[source_id])
    out["available_date"] = (out["observation_date"] + BDay(int(lag_bdays))).dt.normalize()
    return out.sort_values("available_date")[["available_date", "observation_date", source_id]]


def align_to_kospi_calendar(
    calendar: pd.DatetimeIndex,
    series: pd.Series,
    source_id: str,
    lag_bdays: int,
) -> pd.DataFrame:
    available = availability_frame(series, source_id, lag_bdays)
    base = pd.DataFrame({"date": pd.DatetimeIndex(calendar).normalize().sort_values()})
    merged = pd.merge_asof(
        base.sort_values("date"),
        available.sort_values("available_date"),
        left_on="date",
        right_on="available_date",
        direction="backward",
    )
    return merged[["date", "observation_date", "available_date", source_id]]


def build_transformed_frame(
    frozen: pd.DataFrame,
    provider_frames: dict[str, pd.DataFrame],
    lag_policy: dict[str, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frozen = frozen.copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    kospi_live = provider_frames.get("kospi_ohlcv", pd.DataFrame()).copy()
    kospi_live = kospi_live.loc[kospi_live.get("valid", False).astype(bool)].copy() if not kospi_live.empty else kospi_live
    extra_dates = pd.DatetimeIndex([])
    if not kospi_live.empty:
        extra_dates = pd.DatetimeIndex(pd.to_datetime(kospi_live["observation_date"]).dt.normalize())
        extra_dates = extra_dates[extra_dates > frozen["date"].max()]
    calendar = frozen["date"].tolist() + list(extra_dates.unique().sort_values())
    calendar = pd.DatetimeIndex(calendar).unique().sort_values()

    out = pd.DataFrame({"date": calendar})
    frozen_indexed = frozen.set_index("date")
    for col in frozen.columns:
        if col == "date":
            continue
        out[col] = frozen_indexed[col].reindex(calendar).to_numpy()

    if not kospi_live.empty:
        k = kospi_live.set_index(pd.to_datetime(kospi_live["observation_date"]).dt.normalize())
        for src, dst in [("open", "kospi_open"), ("high", "kospi_high"), ("low", "kospi_low"), ("close", "kospi_close")]:
            current = pd.Series(out[dst].to_numpy(dtype=float), index=calendar)
            live = pd.to_numeric(k[src], errors="coerce")
            current.loc[live.index[live.index > frozen["date"].max()]] = live.loc[live.index > frozen["date"].max()]
            out[dst] = current.to_numpy(dtype=float)

    aligned: dict[str, pd.Series] = {}
    latest_rows: list[dict[str, object]] = []
    for source_id in [
        "usdkrw",
        "vix",
        "vix3m",
        "us_10y_real_yield",
        "us_10y_yield",
        "us_2y_yield",
        "us_3m_yield",
        "us_baa_corp_yield",
        "us_aaa_corp_yield",
        "nfci",
    ]:
        live = provider_frames.get(source_id, pd.DataFrame()).copy()
        if live.empty or "observation_date" not in live:
            series = pd.Series(dtype=float)
        else:
            good = live.loc[live["valid"].astype(bool)].copy()
            series = pd.Series(
                pd.to_numeric(good["value"], errors="coerce").to_numpy(dtype=float),
                index=pd.to_datetime(good["observation_date"]).dt.normalize(),
            ).sort_index()
            series = series.loc[~series.index.duplicated(keep="last")]
        if series.empty and source_id in frozen.columns:
            series = pd.Series(pd.to_numeric(frozen[source_id], errors="coerce").to_numpy(dtype=float), index=frozen["date"])
        elif source_id in frozen.columns:
            old = pd.Series(pd.to_numeric(frozen[source_id], errors="coerce").to_numpy(dtype=float), index=frozen["date"])
            series = pd.concat([old, series]).sort_index()
            series = series.loc[~series.index.duplicated(keep="first")]
        aligned_frame = align_to_kospi_calendar(calendar, series, source_id, lag_policy[source_id])
        aligned[source_id] = aligned_frame.set_index("date")[source_id]
        latest_rows.append(
            {
                "source_id": source_id,
                "latest_observation_date": _date_or_none(series.index.max() if len(series) else pd.NaT),
                "latest_available_date": _date_or_none(aligned_frame["available_date"].dropna().max() if len(aligned_frame) else pd.NaT),
            }
        )

    out["usdkrw"] = aligned["usdkrw"].reindex(calendar).to_numpy(dtype=float)
    out["vix"] = aligned["vix"].reindex(calendar).to_numpy(dtype=float)
    out["vix3m"] = aligned["vix3m"].reindex(calendar).to_numpy(dtype=float)
    out["us_10y_real_yield"] = aligned["us_10y_real_yield"].reindex(calendar).to_numpy(dtype=float)
    out["us_10y_yield"] = aligned["us_10y_yield"].reindex(calendar).to_numpy(dtype=float)
    out["us_2y_yield"] = aligned["us_2y_yield"].reindex(calendar).to_numpy(dtype=float)
    out["us_3m_yield"] = aligned["us_3m_yield"].reindex(calendar).to_numpy(dtype=float)
    out["us_baa_corp_yield"] = aligned["us_baa_corp_yield"].reindex(calendar).to_numpy(dtype=float)
    out["us_aaa_corp_yield"] = aligned["us_aaa_corp_yield"].reindex(calendar).to_numpy(dtype=float)
    out["nfci"] = aligned["nfci"].reindex(calendar).to_numpy(dtype=float)

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
    stress_parts = pd.concat(
        [
            rolling_zscore(out.set_index("date")["hy_proxy"]).rename("hy_z"),
            rolling_zscore(out.set_index("date")["nfci"]).rename("nfci_z"),
            rolling_zscore(out.set_index("date")["vix"]).rename("vix_z"),
        ],
        axis=1,
    )
    out["credit_stress_raw"] = stress_parts.mean(axis=1).reindex(pd.to_datetime(out["date"])).to_numpy(dtype=float)
    out["credit_stress_safe"] = -out["credit_stress_raw"]
    out["official_operating_model"] = False

    old_dates = set(pd.to_datetime(frozen["date"]).dt.strftime("%Y-%m-%d"))
    old_mask = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d").isin(old_dates)
    frozen_by_date = frozen.set_index("date")
    for col in frozen.columns:
        if col == "date" or col not in out.columns:
            continue
        restored = pd.Series(out[col].to_numpy(), index=pd.to_datetime(out["date"]).dt.normalize())
        restored.loc[frozen_by_date.index] = frozen_by_date[col]
        out[col] = restored.reindex(pd.to_datetime(out["date"]).dt.normalize()).to_numpy()
    out["live_extension_row"] = ~pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d").isin(old_dates)
    latest = pd.DataFrame(latest_rows)
    return out.sort_values("date").reset_index(drop=True), latest


def _date_or_none(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")
