# KOSPI Macro5 D1-C3A.2 Latest Session Full History Extension

## Gate

PASS_KOSPI_MACRO5_D1C3A2_LATEST_SESSION_FULL_HISTORY_CONNECTED

## Scope

- Base commit: `62a91c8`
- Latest completed KRX session: `2026-07-31`
- Frozen cutoff: `2026-07-28`
- Live tail dates: `2026-07-29`, `2026-07-30`, `2026-07-31`
- UI redesign: false
- CSS/layout/card/table/chart style changes: false
- Macro4 changed: false
- Macro6 changed: false
- Probe changed: false
- New feature/source/candidate/Secret/query/dependency: 0
- Deleted files: 0
- Commit/push/deploy: false

## Runtime History Coverage

- Indicator families: 15 / 15
- Parameterized Core15 components: 47 / 47
- Child Combo1: 17 / 17
- Final Combo1: 4 / 4
- Final Combo2: 5 / 5
- Final9: 9 / 9

## Last Date Checks

- Benchmark last date: `2026-07-31`
- Core component history last date: `2026-07-31`
- Child Combo1 history last date: `2026-07-31`
- Final9 history last date: `2026-07-31`
- Final9 display component history last date: `2026-07-31`
- Snapshot basis date: `2026-07-31`

## Snapshot vs History Last Row

- Raw mismatch: 0
- T+1 mismatch: 0
- Active-count mismatch: 0
- Event mismatch: 0

## Integrity

- Candidate/date duplicate keys: 0
- Core component/date duplicate keys: 0
- Child combo/date duplicate keys: 0
- Display component/date duplicate keys: 0
- Benchmark/date duplicate keys: 0
- Unexpected date gap: 0
- Missing-as-risk-on: 0
- Denominator shrink: 0
- Frozen benchmark overwrite: 0
- Frozen candidate rows preserved: 51,733

## Page Wiring

LIVE_EXTEND:
- candidate raw/T+1 state chart
- candidate active-count and start/end event source
- component ON/OFF state charts
- KOSPI benchmark close overlay
- current state period display

FROZEN_KEEP:
- official CAGR
- official MDD
- official Calmar
- official turnover
- official backtest period
- official performance summary
- Final9 candidate/K/L definitions

Unclear chart semantics: 0

## Live Smoke

- Sources reachable: 11 / 11
- Final9 rows: 9 / 9
- Calculable: 9 / 9
- Freshness-qualified: 9 / 9
- Risk-off count: 9 / 9
- Basis date: `2026-07-31`

## Verification

- `python3 -m py_compile kospi_macro5_runtime/*.py technical_signal_dashboard.py`: PASS
- `python3 -m compileall -q kospi_macro5_runtime tests`: PASS
- `python3 -m pytest -q tests/test_kospi_macro5_d1c3a1_datetime_merge.py tests/test_kospi_macro5_d1c3a2_latest_history.py tests/test_kospi_macro5_d1c2b_cloud_probe_bridge.py tests/test_kospi_macro5_d1c3a_page_wiring.py`: PASS, 14 passed
- Streamlit local startup: PASS at `http://127.0.0.1:8772`

Note: pytest emitted a pandas `FutureWarning` for appending live-only event columns to Frozen reference history. The warning does not change values; avoiding it would require wider historical event schema mutation and was left out of scope.

## Status

AWAITING_USER_APPROVAL_KOSPI_MACRO5_D1C3A2_COMMIT_PUSH
