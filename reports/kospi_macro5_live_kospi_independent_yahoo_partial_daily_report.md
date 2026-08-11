# Macro5 Live KOSPI Independent Yahoo Partial Daily Report

## Gate

PASS_MACRO5_LIVE_KOSPI_INDEPENDENT_YAHOO_PARTIAL_DAILY_READY

## Scope

- Changed only Macro5 KOSPI live source date/freshness handling.
- Kept Frozen assets, Final9 candidates, K/L, T+1, hysteresis, market-stage logic, backtests, charts, and Macro4 unchanged.
- Did not retry Phase 3-C1 payload split.
- Did not commit or push.

## KOSPI Source Route

- Source: Yahoo `^KS11`
- Macro5 route: `yf.download(period=6mo);cache_mode=NORMAL`
- Macro5 runtime now permits a current KRX session row for `kospi_ohlcv` only.
- Current-session permission is derived from `Asia/Seoul` KST and the KRX calendar asset.
- Non-KOSPI sources remain on the existing completed-session / publication-lag policy.

## Live Result

- as_of_utc: `2026-08-11T07:28:04.325591+00:00`
- expected_latest_krx_session: `2026-08-11`
- latest_kospi_live_session: `2026-08-11`
- KOSPI raw latest observation date: `2026-08-11`
- KOSPI selected latest observation date: `2026-08-11`
- KOSPI actual latest available date: `2026-08-11`
- KOSPI freshness status: `FRESH`
- KOSPI latest row final: `true`
- KOSPI live observation type: `completed_daily`
- KOSPI latest close: `6345.52978515625`

## Independent Yahoo Check

- Independent Yahoo `^KS11` latest date: `2026-08-11`
- Independent Yahoo close: `6345.52978515625`
- Macro5 latest KOSPI date/value matched the independent Yahoo route at the measurement time.
- General dashboard normalizer vs Macro5 independent normalizer:
  - rows compared: `20`
  - max absolute OHLC diff: `0.0`
  - general latest date: `2026-08-11`
  - Macro5 latest date: `2026-08-11`
- Intraday exact-price parity is not used as a hard gate because a live daily row can move during market hours.

## KOSPI-Derived Core15 Latest Dates

- `kospi_index_level`: `2026-08-11`
- `kospi_rsi`: `2026-08-11`
- `kospi_bollinger`: `2026-08-11`
- `kospi_hv`: `2026-08-11`
- `kospi_natr`: `2026-08-11`

## Final9 Current State

- calculable candidates: `9 / 9`
- freshness-qualified candidates: `0 / 9`
- calculated raw Risk-off count: `9`
- default candidate: `m10::combo2_m10_k7_l4_bbd8c760d49b44bb`
- default raw state: `1`
- default T+1 position: `0`
- default active count: `10`
- default basis date: `2026-08-11`

The `freshness-qualified` count remains constrained by non-KOSPI required-source freshness. This confirms the KOSPI source was advanced without forcing every candidate's operational freshness gate to pass.

## Validation

- KOSPI current-session row retention unit tests: PASS
- KOSPI source/freshness compile: PASS
- Macro5 live/history/current-state/backtest tests: PASS
- Macro5 chart and Phase2-F detail chart cache tests: PASS
- Macro5 route/isolation smoke: PASS
- Macro6 smoke: PASS
- Frozen assets changed: NO
