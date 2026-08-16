# KOSDAQ Macro7 D2 Live Runtime Validation

- Gate: `PASS_KOSDAQ_MACRO7_D2_LIVE_RUNTIME_READY`
- Mode: independent KOSDAQ runtime; Frozen prefix remains authoritative.
- KRX session: `NON_SESSION_DAY`
- Provisional intraday model state: `NOT_COMPUTED`
- Required family coverage: `15/15`

## Boundary

- last_market_row_date: `2026-08-14`
- last_market_row_status: `FINAL`
- last_valid_close_date: `2026-08-14`
- last_valid_close_value: `864.65`
- latest_completed_session: `2026-08-14`
- frozen_rows_overwritten: `0`
- live_rows_on_or_before_cutoff_used_for_runtime: `0`
- duplicate_date_count: `0`
- live_tail_first_date: `2026-07-29`
- live_tail_last_date: `2026-08-14`
- live_tail_row_count: `13`

## Source Status

| Source | Observation | Available Through | Freshness |
|---|---|---|---|
| kosdaq_ohlcv | 2026-08-14 | 2026-08-14 | FRESH |
| usdkrw | 2026-08-16 | 2026-08-14 | FRESH |
| vix | 2026-08-13 | 2026-08-14 | FRESH |
| vix3m | 2026-08-13 | 2026-08-14 | FRESH |
| us_10y_real_yield | 2026-08-13 | 2026-08-14 | FRESH |
| us_10y_yield | 2026-08-13 | 2026-08-14 | FRESH |
| us_2y_yield | 2026-08-13 | 2026-08-14 | FRESH |
| us_3m_yield | 2026-08-13 | 2026-08-14 | FRESH |
| us_baa_corp_yield | 2026-08-13 | 2026-08-14 | FRESH |
| us_aaa_corp_yield | 2026-08-13 | 2026-08-14 | FRESH |
| nfci | 2026-08-07 | 2026-08-14 | NO_NEW_RELEASE_EXPECTED |

## Final10 Snapshot

| Candidate | Basis | Valid | Raw Risk-off |
|---|---|---:|---:|
| combo1_n10_k8_l5_7d675fa2173be942 | 2026-08-14 | True | True |
| combo1_n9_k7_l5_ef47fc166183b7f0 | 2026-08-14 | True | True |
| combo1_n10_k7_l3_73a7886028ee8ceb | 2026-08-14 | True | True |
| combo1_n9_k6_l3_eb2681f38d934aeb | 2026-08-14 | True | True |
| combo1_n8_k6_l3_68fad8e1263e8016 | 2026-08-14 | True | True |
| combo2_m7_k4_l3_58c1eaea19e6d371 | 2026-08-14 | True | True |
| combo2_m8_k6_l5_9789467e69e7b1e9 | 2026-08-14 | True | True |
| combo2_m5_k3_l2_50e15ab10d6cba46 | 2026-08-14 | True | True |
| combo2_m8_k6_l5_dc78b72794ed82f2 | 2026-08-14 | True | True |
| combo2_m6_k3_l2_32c73aa82d8abc21 | 2026-08-14 | True | True |

## Contract Checks

- Frozen prefix mismatch: `0`
- Boundary state reset: `0`
- Boundary T+1 reset: `0`
- Invalid interpreted as Risk-on: `0`
- Combo2 input: `CHILD_COMBO1_RAW_RISK_STATE`
- Final T+1 application count: `1`
- KOSPI/research runtime isolation hits: `0`
- Immutable baseline drift: `0`

A source observation date is retained as source metadata. Live model rows are KRX calculation trading dates; current segment returns end at each candidate basis date.
