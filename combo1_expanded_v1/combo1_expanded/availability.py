from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pandas as pd
import numpy as np

from .config import AvailabilityPolicy, PipelineConfig


def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int | None = None) -> pd.Series:
    min_p = max(30, int(window) // 4) if min_periods is None else int(min_periods)
    mean = series.rolling(int(window), min_periods=min_p).mean()
    std = series.rolling(int(window), min_periods=min_p).std()
    return ((series - mean) / std.replace(0.0, np.nan)).clip(-3.0, 3.0)


FRED_LAG_SENSITIVE_INDICATORS: tuple[str, ...] = (
    "HY",
    "IG",
    "10Y Real Yield",
    "10Y-2Y Spread",
    "10Y-3M Spread",
    "10Y Nominal Yield Slope",
)


def apply_availability_lag(series: pd.Series, indicator: str, config: PipelineConfig) -> pd.Series:
    """검증용 이용 가능 시점 lag를 적용한다. 기본 lag 0이면 원본 그대로 반환한다."""
    policy = config.availability_policies.get(indicator, AvailabilityPolicy())
    lag = int(policy.lag_bdays)
    if lag <= 0 or series is None or series.empty:
        return series
    shifted = series.copy()
    shifted.index = pd.DatetimeIndex(pd.to_datetime(shifted.index)).normalize() + pd.offsets.BDay(lag)
    shifted = shifted.sort_index()
    return shifted.loc[~shifted.index.duplicated(keep="last")]


def apply_nfci_release_lag(series: pd.Series, config: PipelineConfig) -> pd.Series:
    """NFCI week-ending observation을 이용 가능일로 옮긴다.

    현재는 명시 release-date mapping이 없으므로 week-ending Friday -> following Wednesday,
    즉 BDay(3)을 보수적 fallback으로 사용한다.
    """
    policy = config.availability_policies.get("NFCI", AvailabilityPolicy(lag_bdays=3))
    lag = int(policy.lag_bdays or 3)
    if series is None or series.empty:
        return series
    shifted = series.copy()
    shifted.index = pd.DatetimeIndex(pd.to_datetime(shifted.index)).normalize() + pd.offsets.BDay(lag)
    shifted = shifted.sort_index()
    return shifted.loc[~shifted.index.duplicated(keep="last")]


def build_credit_stress_safe_from_components(
    snapshot: pd.DataFrame,
    config: PipelineConfig,
    zscore_window: int = 252,
    zscore_min_periods: int | None = None,
    require_all_components: bool = True,
) -> pd.Series:
    """HY/NFCI/VIX 구성요소별 이용 가능일을 반영해 Credit Stress safe series를 만든다."""
    required = {"hy_raw", "nfci_raw", "vix_raw"}
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(f"Credit Stress 구성요소 컬럼 누락: {missing}")

    hy_available = apply_availability_lag(snapshot["hy_raw"].dropna(), "HY", config)
    nfci_available = apply_nfci_release_lag(snapshot["nfci_raw"].dropna(), config)
    vix_available = apply_availability_lag(snapshot["vix_raw"].dropna(), "VIX", config)

    parts = pd.concat(
        [
            _rolling_zscore(hy_available, zscore_window, zscore_min_periods).rename("HY"),
            _rolling_zscore(nfci_available, zscore_window, zscore_min_periods).rename("NFCI"),
            _rolling_zscore(vix_available, zscore_window, zscore_min_periods).rename("VIX"),
        ],
        axis=1,
    )
    if require_all_components:
        stress = parts.dropna(how="any").mean(axis=1)
    else:
        stress = parts.mean(axis=1).dropna()
    stress = stress.sort_index()
    stress.name = "credit_stress_raw_available"
    safe = (-stress).rename("credit_stress_safe")
    safe.attrs["credit_stress_component_policy"] = {
        "HY": "lag_bdays=1",
        "NFCI": "week-ending Friday -> following Wednesday fallback BDay(3)",
        "VIX": "lag_bdays=0",
        "require_all_components": bool(require_all_components),
        "derived_from_component_availability": True,
    }
    return safe


def parse_availability_lag_overrides(raw: str | None) -> dict[str, int]:
    """CLI 문자열을 지표별 business-day lag dict로 변환한다.

    예: "HY=1,Credit Stress=2" 또는 "fred=1".
    """
    if not raw:
        return {}
    out: dict[str, int] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"lag override는 name=value 형식이어야 합니다: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if key == "Credit Stress":
            raise ValueError(
                "Credit Stress는 HY/NFCI/VIX 구성요소별 공개시점으로 생성되므로 "
                "Credit Stress=2 같은 단일 lag override를 사용할 수 없습니다."
            )
        lag = int(value.strip())
        if lag < 0:
            raise ValueError("availability lag는 0 이상이어야 합니다.")
        if key.lower() in {"fred", "fred_like", "fred-like"}:
            for indicator in FRED_LAG_SENSITIVE_INDICATORS:
                out[indicator] = lag
        else:
            out[key] = lag
    return out


def with_availability_lags(config: PipelineConfig, overrides: dict[str, int]) -> PipelineConfig:
    if not overrides:
        return config
    policies = dict(config.availability_policies)
    for indicator, lag in overrides.items():
        if indicator == "Credit Stress":
            raise ValueError(
                "Credit Stress 단일 lag는 금지됩니다. HY/NFCI/VIX 구성요소 lag 정책을 사용하세요."
            )
        base = policies.get(indicator, AvailabilityPolicy())
        policies[indicator] = replace(
            base,
            lag_bdays=int(lag),
            status=base.status if base.status != "" else "unverified",
        )
    return replace(config, availability_policies=policies)


def availability_policy_rows(config: PipelineConfig, indicators: Iterable[str] | None = None) -> list[dict[str, object]]:
    names = list(indicators) if indicators is not None else sorted(config.availability_policies)
    rows: list[dict[str, object]] = []
    for name in names:
        policy = config.availability_policies.get(name, AvailabilityPolicy())
        rows.append(
            {
                "indicator": name,
                "availability_lag_bdays": int(policy.lag_bdays),
                "availability_status": policy.status,
                "revision_risk": policy.revision_risk,
                "release_rule": policy.release_rule,
                "derived_from_component_availability": bool(policy.derived_from_component_availability),
                "availability_notes": policy.notes,
            }
        )
    return rows
