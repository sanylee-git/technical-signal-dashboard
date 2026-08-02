from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .live_contracts import SOURCE_CONTRACTS


@dataclass(frozen=True)
class FreshnessContract:
    source_id: str
    provider: str
    provider_series_id: str
    cadence: str
    source_timezone: str
    expected_observation_rule: str
    expected_publication_rule: str
    expected_available_rule: str
    availability_policy_id: str
    krx_alignment_policy_id: str
    max_expected_lag_sessions: int | None
    carry_forward_allowed: bool
    revision_mode: str
    retry_supported: bool
    cache_bypass_supported: bool
    alternate_route_supported: bool
    required_for_families: tuple[str, ...]
    required_for_candidates: str = "derived_from_final9_lineage"


FAMILY_SOURCE_MAP: dict[str, tuple[str, ...]] = {
    "kospi_index_level": ("kospi_ohlcv",),
    "kospi_rsi": ("kospi_ohlcv",),
    "kospi_bollinger": ("kospi_ohlcv",),
    "kospi_natr": ("kospi_ohlcv",),
    "kospi_hv": ("kospi_ohlcv",),
    "usdkrw_level": ("usdkrw",),
    "vix_level": ("vix",),
    "vix_spread": ("vix", "vix3m"),
    "us_10y_real_yield_level": ("us_10y_real_yield",),
    "us_10y_2y_spread": ("us_10y_yield", "us_2y_yield"),
    "us_10y_3m_spread": ("us_10y_yield", "us_3m_yield"),
    "us_10y_slope": ("us_10y_yield",),
    "us_hy_oas_level": ("us_baa_corp_yield", "us_10y_yield"),
    "us_ig_oas_level": ("us_aaa_corp_yield", "us_10y_yield"),
    "global_credit_stress": ("us_baa_corp_yield", "us_10y_yield", "nfci", "vix"),
}


def source_freshness_contracts() -> dict[str, FreshnessContract]:
    contracts: dict[str, FreshnessContract] = {}
    reverse_families: dict[str, list[str]] = {sid: [] for sid in SOURCE_CONTRACTS}
    for family, sources in FAMILY_SOURCE_MAP.items():
        for source_id in sources:
            reverse_families.setdefault(source_id, []).append(family)

    for source_id, base in SOURCE_CONTRACTS.items():
        cadence = "weekly" if source_id == "nfci" else "daily"
        if source_id == "kospi_ohlcv":
            obs_rule = "latest_completed_krx_session"
            avail_rule = "same_completed_krx_session_after_close"
            lag = 0
            tz = "Asia/Seoul"
        elif source_id == "nfci":
            obs_rule = "latest_weekly_observation_available_from_provider"
            avail_rule = "observation_date_plus_3_business_days_aligned_to_krx"
            lag = None
            tz = "America/Chicago"
        else:
            obs_rule = f"latest_provider_daily_observation_with_{base.lag_bdays}_business_day_availability_lag"
            avail_rule = f"observation_date_plus_{base.lag_bdays}_business_days_aligned_to_krx"
            lag = 0
            tz = "America/New_York" if base.provider == "fred" else "UTC"
        contracts[source_id] = FreshnessContract(
            source_id=source_id,
            provider=base.provider,
            provider_series_id=base.provider_series_id,
            cadence=cadence,
            source_timezone=tz,
            expected_observation_rule=obs_rule,
            expected_publication_rule="publication_timestamp_not_available;official_availability_rule_used",
            expected_available_rule=avail_rule,
            availability_policy_id=f"lag_bdays_{base.lag_bdays}",
            krx_alignment_policy_id="asof_to_completed_krx_session",
            max_expected_lag_sessions=lag,
            carry_forward_allowed=source_id != "kospi_ohlcv",
            revision_mode="LATEST_AVAILABLE_HISTORY_WITH_FROZEN_HISTORY_AUTHORITATIVE",
            retry_supported=True,
            cache_bypass_supported=True,
            alternate_route_supported=False,
            required_for_families=tuple(sorted(set(reverse_families.get(source_id, [])))),
        )
    return contracts


def contracts_dataframe() -> pd.DataFrame:
    return pd.DataFrame([asdict(c) for c in source_freshness_contracts().values()])


def required_sources_for_family(indicator_family: str) -> tuple[str, ...]:
    return FAMILY_SOURCE_MAP.get(indicator_family, tuple(SOURCE_CONTRACTS.keys()))
