from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


MarketName = Literal["sp500", "nasdaq"]
IndicatorKind = Literal["level", "yield_slope", "rsi", "bollinger"]


@dataclass(frozen=True)
class MarketSpec:
    key: MarketName
    label: str
    benchmark_ticker: str


MARKETS: dict[MarketName, MarketSpec] = {
    "sp500": MarketSpec("sp500", "S&P500", "^GSPC"),
    "nasdaq": MarketSpec("nasdaq", "Nasdaq", "^IXIC"),
}


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    kind: IndicatorKind
    source_column: str | None = None
    description: str = ""


INDICATOR_SPECS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("Index", "level", "benchmark_close", "시장지수 종가"),
    IndicatorSpec("HY", "level", "hy_safe", "HY OAS 반전"),
    IndicatorSpec("IG", "level", "ig_safe", "IG OAS 반전"),
    IndicatorSpec("Credit Stress", "level", "credit_stress_safe", "HY+NFCI+VIX z-score 반전"),
    IndicatorSpec("VIX", "level", "vix_safe", "VIX 반전"),
    IndicatorSpec("VIX Spread", "level", "vix_spread_safe", "VIX-VIX3M 반전"),
    IndicatorSpec("10Y Real Yield", "level", "real_yield_10y_safe", "DFII10 반전"),
    IndicatorSpec("10Y-2Y Spread", "level", "spread_10y2y", "T10Y2Y"),
    IndicatorSpec("10Y-3M Spread", "level", "spread_10y3m", "T10Y3M"),
    IndicatorSpec("10Y Nominal Yield Slope", "yield_slope", "dgs10", "DGS10 rolling linear-regression slope 반전"),
    IndicatorSpec("RSI", "rsi", None, "시장지수 RSI 동적 10/90 분위수"),
    IndicatorSpec("Bollinger Band", "bollinger", None, "시장지수 Bollinger 재진입"),
)

INDICATOR_ORDER: tuple[str, ...] = tuple(spec.name for spec in INDICATOR_SPECS)
INDICATOR_BY_NAME: dict[str, IndicatorSpec] = {spec.name: spec for spec in INDICATOR_SPECS}


@dataclass(frozen=True)
class AvailabilityPolicy:
    lag_bdays: int = 0
    status: str = "unverified"
    revision_risk: str = "unknown"
    release_rule: str = ""
    derived_from_component_availability: bool = False
    notes: str = ""


def default_availability_policies() -> dict[str, AvailabilityPolicy]:
    """데이터 이용 가능 시점 가정. 백테스트 성과 선택값이 아닌 고정 공개시점 정책."""
    return {
        "Index": AvailabilityPolicy(
            lag_bdays=0,
            status="market_close_proxy",
            revision_risk="low",
            notes="Yahoo benchmark close; treated as available at/after market close.",
        ),
        "HY": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="FRED ICE BofA OAS; observation date may differ from usable publication time.",
        ),
        "IG": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="FRED ICE BofA OAS; observation date may differ from usable publication time.",
        ),
        "Credit Stress": AvailabilityPolicy(
            lag_bdays=0,
            status="derived_component_policy",
            revision_risk="unknown",
            derived_from_component_availability=True,
            notes="Composite is rebuilt from lag-adjusted HY, NFCI, and VIX. No extra indicator-level lag is applied.",
        ),
        "NFCI": AvailabilityPolicy(
            lag_bdays=3,
            status="calendar_fallback",
            revision_risk="unknown",
            release_rule="week-ending Friday -> following Wednesday; fallback BDay(3)",
            notes="Used only inside Credit Stress. Explicit release-date mapping can replace fallback later.",
        ),
        "VIX": AvailabilityPolicy(
            lag_bdays=0,
            status="market_close_proxy",
            revision_risk="low",
            notes="Yahoo ^VIX close; treated as market close data.",
        ),
        "VIX Spread": AvailabilityPolicy(
            lag_bdays=0,
            status="market_close_proxy",
            revision_risk="low",
            notes="Yahoo ^VIX minus ^VIX3M close; treated as market close data.",
        ),
        "10Y Real Yield": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="FRED DFII10/H.15; publication timing should be checked before full run.",
        ),
        "10Y-2Y Spread": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="FRED T10Y2Y; publication timing should be checked before full run.",
        ),
        "10Y-3M Spread": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="FRED T10Y3M; publication timing should be checked before full run.",
        ),
        "10Y Nominal Yield Slope": AvailabilityPolicy(
            lag_bdays=1,
            status="unverified",
            revision_risk="unknown",
            notes="Derived from FRED DGS10; publication timing should be checked before full run.",
        ),
        "RSI": AvailabilityPolicy(
            lag_bdays=0,
            status="market_close_proxy",
            revision_risk="low",
            notes="Derived from benchmark close.",
        ),
        "Bollinger Band": AvailabilityPolicy(
            lag_bdays=0,
            status="market_close_proxy",
            revision_risk="low",
            notes="Derived from benchmark OHLC.",
        ),
    }


@dataclass(frozen=True)
class LevelGrid:
    ema_spans: tuple[int, ...] = (1, 5, 10, 20, 40, 80)
    rolling_windows: tuple[int, ...] = (30, 60, 120, 240, 480)
    start_quantiles: tuple[float, ...] = (0.20, 0.35, 0.50, 0.75, 0.90)
    end_quantiles: tuple[float, ...] = (0.10, 0.25, 0.40, 0.65, 0.80)


@dataclass(frozen=True)
class RSIGrid:
    periods: tuple[int, ...] = (7, 14, 28, 56)
    lookbacks: tuple[int, ...] = (20, 40, 80, 160, 320)
    lower_quantile: float = 0.10
    upper_quantile: float = 0.90


@dataclass(frozen=True)
class BollingerGrid:
    windows: tuple[int, ...] = (10, 20, 40, 80, 160)
    std_multipliers: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0)


@dataclass(frozen=True)
class YieldSlopeGrid:
    slope_windows: tuple[int, ...] = (5, 10, 20, 40, 80, 160)
    ema_spans: tuple[int, ...] = (1, 5, 10, 20, 40, 80)
    threshold_windows: tuple[int, ...] = (30, 60, 120, 240, 480)
    start_quantiles: tuple[float, ...] = (0.20, 0.35, 0.50, 0.75, 0.90)
    end_quantiles: tuple[float, ...] = (0.10, 0.25, 0.40, 0.65, 0.80)


@dataclass(frozen=True)
class CandidateRules:
    # 모든 후보에 적용되는 최소 유효성 검사
    minimum_data_coverage: float = 0.90
    minimum_cycle_count: int = 1
    minimum_risk_off_share: float = 0.0
    maximum_risk_off_share: float = 0.70

    # 안정형 후보 그룹에 적용되는 필터. 20Y 결과를 기준으로 사용한다.
    stability_reference_years: int = 20
    stability_minimum_cycle_count: int = 5
    stability_maximum_short_cycle_ratio: float = 0.10
    stability_maximum_risk_off_share: float = 0.30
    short_cycle_days_exclusive: int = 10

    # 후보 그룹당 종합/MDD/최종자산 각 1개
    maximum_candidates_per_group: int = 3


@dataclass(frozen=True)
class CompositeScoreWeights:
    return_weight: float = 0.40
    mdd_defense_weight: float = 0.35
    consistency_weight: float = 0.15
    risk_off_efficiency_weight: float = 0.10
    ten_year_weight: float = 0.40
    twenty_year_weight: float = 0.60


@dataclass(frozen=True)
class PracticalRankingPolicy:
    minimum_cycle_count_10y: int = 5
    minimum_cycle_count_20y: int = 5
    minimum_risk_off_share: float = 0.0
    maximum_risk_off_share: float = 0.50
    return_maximum_mdd_20y: float = -0.30
    stable_maximum_short_cycle_ratio_10y: float = 0.30
    stable_maximum_short_cycle_ratio_20y: float = 0.30
    strict_maximum_risk_off_share: float = 0.30
    strict_maximum_short_cycle_ratio_10y: float = 0.10
    strict_maximum_short_cycle_ratio_20y: float = 0.10


@dataclass(frozen=True)
class SearchSettings:
    evaluation_years: tuple[int, int] = (10, 20)
    fetch_warmup_years: int = 4
    initial_capital: float = 100.0
    search_rounds: int = 2
    refinement_seed_count: int = 12
    refinement_max_values_per_dimension: int = 7


@dataclass(frozen=True)
class ComboSettings:
    min_combo_size: int = 2
    max_combo_size: int = 6
    detail_top_n: int = 1000
    maximum_evaluations_without_force: int = 5_000_000
    chunk_rows: int = 100_000


@dataclass(frozen=True)
class PipelineConfig:
    level_grid: LevelGrid = field(default_factory=LevelGrid)
    rsi_grid: RSIGrid = field(default_factory=RSIGrid)
    bollinger_grid: BollingerGrid = field(default_factory=BollingerGrid)
    yield_slope_grid: YieldSlopeGrid = field(default_factory=YieldSlopeGrid)
    candidate_rules: CandidateRules = field(default_factory=CandidateRules)
    score_weights: CompositeScoreWeights = field(default_factory=CompositeScoreWeights)
    practical_ranking_policy: PracticalRankingPolicy = field(default_factory=PracticalRankingPolicy)
    search: SearchSettings = field(default_factory=SearchSettings)
    combo: ComboSettings = field(default_factory=ComboSettings)
    availability_policies: dict[str, AvailabilityPolicy] = field(default_factory=default_availability_policies)
    vintage_mode: str = "latest_available_history"
    point_in_time_vintage: bool = False
    revision_risk_acknowledged: bool = True
    credit_stress_component_policy: str = "all_components_required_after_component_availability_lag"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_output_dir(base_dir: str | Path, market: MarketName) -> Path:
    return Path(base_dir).expanduser().resolve() / market
