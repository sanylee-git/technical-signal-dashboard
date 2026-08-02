from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SourceContract:
    source_id: str
    provider: str
    provider_series_id: str
    lag_bdays: int
    value_column: str
    frozen_columns: tuple[str, ...]
    frequency: str = "daily"


SOURCE_CONTRACTS: dict[str, SourceContract] = {
    "kospi_ohlcv": SourceContract("kospi_ohlcv", "yahoo", "^KS11", 0, "close", ("kospi_open", "kospi_high", "kospi_low", "kospi_close")),
    "usdkrw": SourceContract("usdkrw", "yahoo", "KRW=X", 1, "close", ("usdkrw_safe",)),
    "vix": SourceContract("vix", "fred", "VIXCLS", 1, "value", ("vix_safe",)),
    "vix3m": SourceContract("vix3m", "fred", "VXVCLS", 1, "value", ("vix_spread_safe",)),
    "us_10y_real_yield": SourceContract("us_10y_real_yield", "fred", "DFII10", 1, "value", ("real_yield_10y_safe",)),
    "us_10y_yield": SourceContract("us_10y_yield", "fred", "DGS10", 1, "value", ("us_10y_yield", "us_10y_2y_spread", "us_10y_3m_spread", "hy_safe", "ig_safe")),
    "us_2y_yield": SourceContract("us_2y_yield", "fred", "DGS2", 1, "value", ("us_10y_2y_spread",)),
    "us_3m_yield": SourceContract("us_3m_yield", "fred", "DGS3MO", 1, "value", ("us_10y_3m_spread",)),
    "us_baa_corp_yield": SourceContract("us_baa_corp_yield", "fred", "DBAA", 1, "value", ("hy_safe",)),
    "us_aaa_corp_yield": SourceContract("us_aaa_corp_yield", "fred", "DAAA", 1, "value", ("ig_safe",)),
    "nfci": SourceContract("nfci", "fred", "NFCI", 3, "value", ("credit_stress_safe",), frequency="weekly"),
}


DERIVED_COLUMNS = {
    "vix_spread_safe": "safe = -(VIXCLS - VXVCLS)",
    "real_yield_10y_safe": "safe = -DFII10",
    "hy_safe": "safe = -(DBAA - DGS10)",
    "ig_safe": "safe = -(DAAA - DGS10)",
    "credit_stress_safe": "safe = -mean(rolling_zscore(hy_proxy), rolling_zscore(NFCI), rolling_zscore(VIXCLS))",
    "us_10y_2y_spread": "DGS10 - DGS2",
    "us_10y_3m_spread": "DGS10 - DGS3MO",
}


REQUIRED_TRANSFORMED_COLUMNS = [
    "date",
    "kospi_open",
    "kospi_high",
    "kospi_low",
    "kospi_close",
    "usdkrw_safe",
    "vix_safe",
    "vix_spread_safe",
    "real_yield_10y_safe",
    "hy_safe",
    "ig_safe",
    "credit_stress_safe",
    "us_10y_2y_spread",
    "us_10y_3m_spread",
    "us_10y_yield",
]


def contracts_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_id": c.source_id,
                "provider": c.provider,
                "provider_series_id": c.provider_series_id,
                "availability_lag_bdays": c.lag_bdays,
                "value_column": c.value_column,
                "frozen_column_names": "|".join(c.frozen_columns),
                "frequency": c.frequency,
            }
            for c in SOURCE_CONTRACTS.values()
        ]
    )


def load_yaml_source_policy(path: Path) -> dict[str, Any]:
    import yaml

    with path.open() as f:
        return yaml.safe_load(f)
