# Macro5 Provider Timing Trace

## 1. Timing Trace Gate

`PASS_MACRO5_PROVIDER_TIMING_TRACE_CAPTURED`

Timing trace was captured without modifying production code, tests, assets, config, cache policy, provider order, timeout, retry, fallback, freshness, availability, signal calculation, UI, or chart logic.

The originally observed "about 23 seconds" was not reproduced exactly. This run was slower: **44.823 seconds**. The measured cause is clear: **sequential FRED provider calls, plus BYPASS calls triggered by STALE freshness on 8 daily FRED sources**.

## 2. Git 기준 상태

| 항목 | 값 |
|---|---|
| repo | `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard` |
| branch | `main` |
| HEAD | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| recorded origin/main | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| expected existing untracked | `reports/macro5_phase3c1_payload_split_failure_rca.md` |
| expected existing untracked | `reports/macro5_provider_fetch_retry_23s_bottleneck_analysis.md` |

`git fetch`, `git pull`, checkout, reset, clean, stash, commit, push, deploy were not executed.

## 3. 측정 방법

Production code was not edited. A diagnostic harness was created outside the repo:

```text
/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_provider_timing_trace_20260811.py
```

Raw trace output:

```text
/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_provider_timing_trace_20260811.json
```

The harness imported the real Macro5 live path:

```python
kospi_macro5_runtime.page_adapter.load_macro5_live_page_data()
```

It wrapped only observation points:

- `page_adapter.fetch_with_optional_bypass`
- `page_adapter.fetch_source`
- `requests.sessions.Session.get`
- `yfinance.download`
- `yfinance.Ticker.history`

Wrapper contract:

- same args / kwargs
- return original result unchanged
- exceptions re-raised unchanged
- no timeout/retry/cache/fallback/provider/query modification
- no secret/token/cookie logging

## 4. Production Code Zero-Diff 확인

Production files were not modified.

Allowed repo write from this task:

```text
reports/macro5_provider_timing_trace.md
```

No code/test/asset/config write was performed.

## 5. 실제 Macro5 호출 경로

Measured path:

```text
page_adapter.load_macro5_live_page_data()
  -> for SOURCE_CONTRACTS:
       fetch_with_optional_bypass(...)
         -> fetch_source(...)
            -> fetch_yahoo(...) or fetch_fred(...)
       evaluate_source_freshness(...)
       normalize_provider_dates_for_freshness(...)
       evaluate_source_freshness(...)
  -> build_transformed_frame(...)
  -> compute_live_tree(...)
  -> source_status_rows(...)
  -> build_final9_snapshot(...)
  -> qualify_candidates(...)
  -> candidate/history payloads
```

The Streamlit `st.cache_data` wrapper was not used by the harness, because this was a direct live-loader timing trace. This is appropriate for provider bottleneck measurement, but it does not measure a Streamlit warm-cache render.

## 6. Top-Level Elapsed

| 항목 | 시간 |
|---|---:|
| Macro5 live loader total | `44.823s` |
| source_total event sum | `37.261s` |
| provider primitive network sum | `36.871s` |
| FRED HTTP GET sum | `35.832s` |
| Yahoo download sum | `1.039s` |
| non-network remainder | `7.952s` |
| trace event count | `49` |

`non-network remainder` includes frozen asset reads, KRX calendar/session preparation, freshness/date normalization, transformed-source construction, Core15 replay, child Combo1 replay, Final9 replay, snapshot construction, candidate qualification, history payload assembly, Python overhead, and trace overhead.

## 7. Provider / Source별 Timing

### Source total

| rank | source_id | provider | series | elapsed_s | retry_executed | selected_attempt | selected_reason |
|---:|---|---|---|---:|---|---:|---|
| 1 | `us_2y_yield` | fred | `DGS2` | `6.397` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 2 | `us_aaa_corp_yield` | fred | `DAAA` | `5.956` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 3 | `us_baa_corp_yield` | fred | `DBAA` | `5.842` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 4 | `us_3m_yield` | fred | `DGS3MO` | `5.234` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 5 | `us_10y_yield` | fred | `DGS10` | `4.284` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 6 | `vix` | fred | `VIXCLS` | `4.072` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 7 | `us_10y_real_yield` | fred | `DFII10` | `2.745` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 8 | `vix3m` | fred | `VXVCLS` | `1.483` | True | 1 | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| 9 | `kospi_ohlcv` | yahoo | `^KS11` | `0.792` | False | 1 | `INITIAL_ATTEMPT` |
| 10 | `usdkrw` | yahoo | `KRW=X` | `0.259` | False | 1 | `INITIAL_ATTEMPT` |
| 11 | `nfci` | fred | `NFCI` | `0.198` | False | 1 | `INITIAL_ATTEMPT` |

### Slowest provider primitives

| rank | primitive | source_id | cache_mode | elapsed_s | timeout | status |
|---:|---|---|---|---:|---:|---|
| 1 | FRED HTTP GET | `us_3m_yield` | BYPASS | `4.853` | 20 | success |
| 2 | FRED HTTP GET | `us_2y_yield` | BYPASS | `3.680` | 20 | success |
| 3 | FRED HTTP GET | `us_10y_yield` | BYPASS | `3.664` | 20 | success |
| 4 | FRED HTTP GET | `us_aaa_corp_yield` | NORMAL | `3.478` | 20 | success |
| 5 | FRED HTTP GET | `us_baa_corp_yield` | BYPASS | `3.022` | 20 | success |
| 6 | FRED HTTP GET | `us_baa_corp_yield` | NORMAL | `2.753` | 20 | success |
| 7 | FRED HTTP GET | `us_2y_yield` | NORMAL | `2.672` | 20 | success |
| 8 | FRED HTTP GET | `vix` | BYPASS | `2.579` | 20 | success |
| 9 | FRED HTTP GET | `us_aaa_corp_yield` | BYPASS | `2.430` | 20 | success |
| 10 | FRED HTTP GET | `us_10y_real_yield` | BYPASS | `2.405` | 20 | success |

Yahoo primitives:

| source_id | route | elapsed_s |
|---|---|---:|
| `kospi_ohlcv` | `yf.download(start=2026-01-04,end=2026-08-12,interval=1d)` | `0.783` |
| `usdkrw` | `yf.download(period=6mo)` | `0.255` |

No `yf.Ticker.history` BYPASS call occurred in this run.

## 8. 실제 Retry / Fallback 발생 여부

There is no generic retry loop. The measured retry-like behavior was the existing STALE-triggered BYPASS path.

| 항목 | 결과 |
|---|---|
| STALE-triggered BYPASS executed | Yes |
| BYPASS source count | 8 |
| BYPASS selected as final attempt | 0 |
| selected attempt for all sources | 1 |
| selected reason for BYPASS sources | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| exception count | 0 |
| timeout exception count | 0 |
| fallback provider used | none |

Daily FRED sources with BYPASS:

```text
vix
vix3m
us_10y_real_yield
us_10y_yield
us_2y_yield
us_3m_yield
us_baa_corp_yield
us_aaa_corp_yield
```

`nfci` did not execute BYPASS because its status was `NO_NEW_RELEASE_EXPECTED`.

## 9. Cold-like / Warm 결과

Only one cold-like live-loader run was executed.

A second run in the same harness would call `page_adapter.load_macro5_live_page_data()` directly again and would not represent the Streamlit `st.cache_data` warm-cache route. Therefore it was not used as a warm-cache measurement.

The actual Streamlit page has a wrapper:

```python
@st.cache_data(ttl=3600, show_spinner=False)
def _load_macro5_kospi_live_page_data_cached(sync_bucket: str):
    return load_macro5_live_page_data()
```

So a true warm Streamlit render should avoid the provider path if the cache key is unchanged. This needs an in-app or Streamlit-aware timing trace if warm-render timing is required.

## 10. 약 23초의 정확한 구성

This run did not reproduce 23 seconds; it reproduced a slower 44.823 seconds.

The composition was:

```text
Macro5 live loader total          44.823s
FRED HTTP GET total               35.832s
Yahoo download total               1.039s
Non-network remainder              7.952s
```

The previous FRED sequential-call hypothesis is confirmed, but the exact mechanism is more specific:

```text
FRED daily sources stale
  -> NORMAL FRED request
  -> freshness == STALE
  -> BYPASS FRED request
  -> BYPASS not newer/fresh
  -> selected attempt remains NORMAL
```

This doubles the FRED daily source calls from 8 to 16, plus NFCI 1 call, for **17 FRED HTTP GET calls**.

## 11. 가장 큰 Bottleneck

The largest single source total was:

```text
us_2y_yield / DGS2 = 6.397s
```

But the larger bottleneck is not one source. It is:

```text
8 stale daily FRED sources
× NORMAL + BYPASS sequential HTTP GET
= 16 daily FRED HTTP calls
```

No individual call reached the 20s timeout. The slowdown is accumulated sequential latency.

## 12. 이전 FRED 9개 순차 호출 가설 검증

| 이전 가설 | 측정 결과 |
|---|---|
| FRED 9개 source가 순차 호출됨 | confirmed |
| 각 FRED call은 `timeout=20` | confirmed |
| 한 source가 20초 timeout에 근접할 수 있음 | not observed in this run |
| 약 23초의 대부분이 FRED일 가능성 | confirmed directionally |
| 실제 source 특정 필요 | done: cumulative FRED stale/BYPASS, slowest source DGS2 |

## 13. Network vs Non-Network 비중

| bucket | elapsed_s | share |
|---|---:|---:|
| provider primitive network | `36.871` | `82.3%` |
| non-network remainder | `7.952` | `17.7%` |

Network/provider latency is the dominant bottleneck.

## 14. 다음 SAFE 최적화 후보

Do not change timeout, retry, fallback, provider order, freshness, or TTL as a "quick fix".

Recommended next steps:

1. **Provider trace metadata optional integration**  
   Metadata-only, no behavior change. Useful if Cloud timing needs continuous confirmation.

2. **FRED Session reuse parity pilot**  
   A single per-run `requests.Session()` for FRED calls may reduce connection overhead. It must prove:
   - same URL
   - same params
   - same timeout
   - same response text hash
   - same normalized DataFrame
   - same Final9 output

3. **FRED parallel fetch parity pilot**  
   Potentially higher impact than session reuse because the bottleneck is accumulated sequential latency. Must prove exact source/transformed/Core15/Final9 parity and deterministic source_rows order.

4. **FRED STALE/BYPASS policy review**  
   This is not a safe optimization by itself. It can reduce large time only by changing when BYPASS is triggered, which may alter freshness defense. Treat as contract review, not simple performance patch.

## 15. 다음 단계 진행 가능 여부

Proceed to implementation only with a parity-locked micro-stage.

Safest implementation order:

```text
Stage P1: FRED Session Reuse parity pilot
Stage P2: FRED parallel fetch parity pilot
Stage P3: FRED stale/BYPASS policy review only if still needed
```

If the user wants the fastest practical improvement, P2 likely has the largest payoff, but it is higher risk than P1 and needs stronger tests.

## 16. Final Answers

1. **가장 느린 provider/source는 무엇인가?**  
   Single source: `us_2y_yield / DGS2`, `6.397s`. Overall: daily FRED stale/BYPASS sequence.

2. **약 23초 중 몇 초를 차지하는가?**  
   This run was `44.823s`, not 23s. FRED HTTP GET consumed `35.832s`.

3. **timeout 근접 호출인가?**  
   No. All calls succeeded; no exception or timeout was observed.

4. **retry가 실제 발생했는가?**  
   Yes, STALE-triggered BYPASS occurred for 8 FRED daily sources.

5. **fallback이 실제 발생했는가?**  
   No fallback provider was used. BYPASS was attempted but rejected as not better.

6. **FRED 9개 직렬 호출 가설이 맞았는가?**  
   Yes. More specifically, it became 17 FRED HTTP calls due to BYPASS.

7. **하나의 source가 대부분을 차지하는가?**  
   No. Multiple FRED calls accumulated.

8. **여러 source의 작은 지연이 누적된 것인가?**  
   Yes.

9. **network 외 계산 병목도 존재하는가?**  
   Non-network remainder was `7.952s`, meaningful but secondary.

10. **warm run에서는 어떻게 달라지는가?**  
    Not measured. Direct `page_adapter` rerun would not represent Streamlit warm cache.

## 17. 작업 범위 확인

- production code/test/asset/config changes: none
- timeout/retry/cache/provider/fallback changes: none
- Streamlit page code changes: none
- commit/push/deploy: none

