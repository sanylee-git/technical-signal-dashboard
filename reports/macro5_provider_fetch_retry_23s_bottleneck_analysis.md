# Macro5 Provider Fetch/Retry 23s Bottleneck Analysis

## 1. Analysis Gate

`INCONCLUSIVE_NEED_RUNTIME_TIMING_TRACE`

코드 기준으로 23초 병목이 발생할 수 있는 위치는 확인했다. 다만 이번 작업은 pytest, Streamlit 실행, network benchmark, provider 실제 호출이 모두 금지된 READ-ONLY 감사였으므로, 특정 provider 1개가 실제로 23초를 소비했다고 확정하지 않는다.

가장 가능성이 높은 구조적 원인은 `FRED` provider 9개를 순차 호출하면서 각 호출이 `requests.get(..., timeout=20)`을 사용한다는 점이다. FRED 1개 요청이 timeout에 근접하면 나머지 처리 오버헤드를 포함해 관찰된 약 23초와 잘 맞는다.

## 2. Git 기준 상태

| 항목 | 값 |
|---|---|
| branch | `main` |
| HEAD | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| recorded origin/main | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| latest commit | `b90c609 Highlight latest KOSPI point on Macro5 charts` |
| KOSPI partial row commit | `d0aba7e Allow Macro5 KOSPI live partial daily row` |
| problem commit present | `5cc4e0c Split Macro5 summary and selected detail payload` |
| rollback commit present | `d385b8e Revert "Split Macro5 summary and selected detail payload"` |
| allowed untracked file | `reports/macro5_phase3c1_payload_split_failure_rca.md` |

`git fetch`, `git pull`, 테스트 실행, Streamlit 실행, provider 호출은 수행하지 않았다.

## 3. Macro5 Provider Fetch 호출 구조

현재 Macro5 page path는 아래 구조다.

```text
technical_signal_dashboard.py
render_macro5_kospi_section
  -> _load_macro5_kospi_live_page_data_cached(sync_bucket)
     -> kospi_macro5_runtime.page_adapter.load_macro5_live_page_data()
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
        -> history payloads for table/chart
```

코드 위치:

| 단계 | 파일 / 함수 | 코드 기준 | network | cache |
|---|---|---:|---|---|
| Streamlit page render | `technical_signal_dashboard.py::render_macro5_kospi_section` | `16844-17284` | 간접 | live payload cache 사용 |
| live payload cache | `technical_signal_dashboard.py::_load_macro5_kospi_live_page_data_cached` | `13763-13767` | 간접 | `st.cache_data(ttl=3600)` + `sync_bucket` |
| live page adapter | `kospi_macro5_runtime/page_adapter.py::load_macro5_live_page_data` | `24-130` | 예 | 없음 |
| source loop | `load_macro5_live_page_data` | `35-97` | 예 | caller cache에 의존 |
| retry/bypass | `kospi_macro5_runtime/retry.py::fetch_with_optional_bypass` | `37-91` | 예 | fetcher에 의존 |
| provider dispatch | `kospi_macro5_runtime/live_sources.py::fetch_source` | `301-312` | 예 | 없음 |
| Yahoo fetch | `fetch_yahoo`, `_fetch_kospi_yahoo_ohlcv` | `218-272` | 예 | 없음 |
| FRED fetch | `fetch_fred` | `275-298` | 예 | 없음 |
| availability merge | `live_availability.py::build_transformed_frame` | `56-172` | 아니오 | 없음 |
| Core15/Combo replay | `live_engine.py::compute_live_tree` | `53-88` | 아니오 | 없음 |

Cloud probe route는 별도 query parameter에서만 실행된다.

```text
?macro5_probe=1
  -> streamlit_cloud_probe_bridge.handle_kospi_macro5_cloud_probe
  -> cloud_probe.run_kospi_macro5_cloud_probe
```

일반 Macro5 page render에서 `cloud_probe.py`를 직접 호출하지 않는다.

## 4. Provider별 역할

`SOURCE_CONTRACTS`는 총 11개 source다.

| source_id | provider | series | lag_bdays | frequency | 역할 |
|---|---|---|---:|---|---|
| `kospi_ohlcv` | yahoo | `^KS11` | 0 | daily | KOSPI OHLC, RSI/Bollinger/NATR/HV/benchmark |
| `usdkrw` | yahoo | `KRW=X` | 1 | daily | USD/KRW safe |
| `vix` | fred | `VIXCLS` | 1 | daily | VIX safe, credit stress part |
| `vix3m` | fred | `VXVCLS` | 1 | daily | VIX spread |
| `us_10y_real_yield` | fred | `DFII10` | 1 | daily | real yield safe |
| `us_10y_yield` | fred | `DGS10` | 1 | daily | 10Y, 10Y-2Y, 10Y-3M, HY/IG proxy base |
| `us_2y_yield` | fred | `DGS2` | 1 | daily | 10Y-2Y |
| `us_3m_yield` | fred | `DGS3MO` | 1 | daily | 10Y-3M |
| `us_baa_corp_yield` | fred | `DBAA` | 1 | daily | HY proxy |
| `us_aaa_corp_yield` | fred | `DAAA` | 1 | daily | IG proxy |
| `nfci` | fred | `NFCI` | 3 | weekly | Credit Stress |

Final9 후보별 required source는 component 구성에 따라 다르다. 그러나 현재 live payload 생성은 후보 선택 여부와 무관하게 `SOURCE_CONTRACTS` 11개 전체를 fetch한다.

## 5. Timeout / Retry / Fallback 구조

### Yahoo

`fetch_yahoo`는 `yfinance`를 사용한다.

- KOSPI NORMAL: `yf.download(^KS11, start=..., end=..., interval=1d, threads=False)`
- KOSPI BYPASS: `yf.Ticker(^KS11).history(start=..., end=..., interval=1d)`
- 일반 Yahoo source NORMAL: `yf.download(period=6mo, threads=False)`
- 일반 Yahoo source BYPASS: `yf.Ticker(...).history(period=6mo)`

코드상 명시 timeout은 없다. yfinance 내부 timeout은 이 코드만으로 확정할 수 없다.

### FRED

`fetch_fred`는 source마다 다음을 호출한다.

```python
requests.Session().get(
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>",
    timeout=20,
)
```

각 FRED source마다 새 `requests.Session()`을 만든다. 총 FRED source는 9개다.

### Retry / Bypass

`fetch_with_optional_bypass`는 일반 retry loop가 아니다.

1. NORMAL 1회 fetch
2. `evaluate_source_freshness`
3. freshness가 정확히 `STALE`이면 BYPASS 1회 추가 fetch
4. BYPASS가 더 최신이거나 fresh이면 BYPASS 결과 선택
5. 아니면 NORMAL 결과 유지

`FETCH_ERROR`, `SCHEMA_ERROR`, `INVALID_VALUE`에 대해서는 코드상 BYPASS가 실행되지 않는다. 즉, timeout으로 `TEMPORARY_FETCH_FAILURE`가 발생하면 freshness status는 `FETCH_ERROR`가 되고 추가 BYPASS는 없다.

## 6. 약 23초 병목 구성 분석

코드상 확정 가능한 내용:

1. live payload cache miss 시 11개 source를 순차 fetch한다.
2. 그중 9개가 FRED이고, 각각 `timeout=20`을 가진다.
3. FRED 요청 하나가 timeout에 근접하면 약 20초가 소비된다.
4. 여기에 KOSPI/Yahoo, 나머지 FRED 빠른 응답, normalization, availability, Core15/Combo 계산, Streamlit overhead가 더해지면 약 23초 관찰값이 가능하다.
5. stale source가 있으면 해당 source는 NORMAL + BYPASS 2회 호출될 수 있어 시간이 더 늘 수 있다.

코드상 확정할 수 없는 내용:

- 실제로 어떤 FRED series가 느렸는지
- Yahoo와 FRED 중 어느 provider가 23초의 대부분을 썼는지
- timeout이 실제 발생했는지, 단순 slow response였는지
- cache miss에서만 발생했는지, cache hit에서도 일부 발생했는지
- Cloud 네트워크 환경에서 특정 provider route가 반복적으로 느린지

따라서 현재 Gate는 `PASS`가 아니라 `INCONCLUSIVE_NEED_RUNTIME_TIMING_TRACE`다.

## 7. 중복 Fetch 여부

확인된 중복 또는 중복 후보:

| 항목 | 판단 | 근거 |
|---|---|---|
| 같은 source를 한 `load_macro5_live_page_data` 실행 안에서 2회 이상 fetch | 명확한 중복 없음 | source loop는 `SOURCE_CONTRACTS.items()` 1회 |
| stale 시 NORMAL + BYPASS | 의도된 freshness 방어 | `STALE`일 때만 추가 호출 |
| source별 `evaluate_source_freshness` 2회 | 의미 있는 2단계 평가 | raw 기준 expected date 계산 후 selected frame 기준 재평가 |
| FRED source 9개를 개별 HTTP request | 최적화 후보 | 같은 provider/endpoint를 여러 series별로 순차 요청 |
| page route와 cloud probe route | 일반 render 중복 아님 | probe query param일 때만 별도 실행 |
| frozen asset read와 live payload generation | 일부 분리 필요 | frozen UI assets는 별도 cache, live payload는 60분 bucket cache |

순수하게 “결과 의미 변경 없이 제거 가능한 명백한 중복 fetch”는 현재 코드만으로는 확인되지 않았다. 가장 큰 개선 후보는 중복 제거보다 FRED 요청 방식/순서/세션/병렬화다.

## 8. Cache 구조

| 함수 | cache | 의미 |
|---|---|---|
| `_load_macro5_kospi_frozen_assets` | `st.cache_data(show_spinner=False)` | Frozen UI assets |
| `_macro5_kospi_build_backtest_stats_cached` | `st.cache_data(show_spinner=False)` | Frozen backtest summary |
| `_macro5_kospi_load_core15_metadata_cached` | `st.cache_data(ttl=3600)` | Core15 metadata |
| `_macro5_kospi_load_transformed_source_cached` | `st.cache_data(ttl=3600)` | Frozen transformed source fallback |
| `_load_macro5_kospi_live_page_data_cached(sync_bucket)` | `st.cache_data(ttl=3600)` | Full live payload |
| `_macro5_kospi_build_component_chart_cached` | custom dict cache | selected component chart |

중요 관찰:

- live payload cache key에는 `sync_bucket`이 들어간다.
- `sync_bucket`은 `_macro_sync_bucket(60)`이라 60분 단위로 바뀐다.
- cache miss가 발생하면 11개 provider 전체 fetch가 실행된다.
- provider 개별 fetch에는 `st.cache_data`가 없다.
- `fetch_source`, `fetch_yahoo`, `fetch_fred`는 Streamlit cache 바깥에 있다.
- TTL을 바꾸는 것은 freshness 의미를 바꿀 수 있으므로 이번 감사에서는 `UNSAFE / DO NOT TOUCH`로 둔다.

## 9. Provider Contract

| source_id | must/fallback 분류 | 실패 영향 |
|---|---|---|
| `kospi_ohlcv` | 반드시 필요 | KOSPI 파생지표와 benchmark 최신 tail 계산 불가 |
| `usdkrw` | 후보 의존 source | USD/KRW 포함 후보 freshness/calculation 제약 |
| `vix` | 후보 의존 source | VIX, credit stress, vix spread 관련 후보 제약 |
| `vix3m` | 후보 의존 source | VIX spread 후보 제약 |
| `us_10y_real_yield` | 후보 의존 source | real yield 후보 제약 |
| `us_10y_yield` | 후보 의존 source | slope, spread, HY/IG proxy 후보 제약 |
| `us_2y_yield` | 후보 의존 source | 10Y-2Y 후보 제약 |
| `us_3m_yield` | 후보 의존 source | 10Y-3M 후보 제약 |
| `us_baa_corp_yield` | 후보 의존 source | HY proxy 후보 제약 |
| `us_aaa_corp_yield` | 후보 의존 source | IG proxy 후보 제약 |
| `nfci` | weekly 후보 의존 source | credit stress 후보는 weekly cadence/freshness 제약 |

현재 runtime은 source 실패를 특정 Risk-on/off로 해석하지 않는다. `build_transformed_frame`은 provider frame이 비어 있으면 frozen series를 사용해 alignment를 계속 만들 수 있지만, source freshness와 candidate qualification은 별도로 기록된다. 후보별 calculable/freshness status는 `qualify_candidates`에서 분리된다.

## 10. SAFE 최적화 후보

아래는 결과 의미를 바꾸지 않을 가능성이 높은 후보지만, 구현 전 parity test는 필요하다.

| 후보 | 기대 효과 | 위험 |
|---|---|---|
| provider timing trace 추가 | 23초 실제 원인 확정 | 계산 결과 영향 없음. 단, instrumentation만 추가해야 함 |
| FRED `requests.Session()`을 source마다 새로 만들지 않고 한 live payload run 안에서 재사용 | handshake/connection overhead 감소 가능 | query/response parity 필요 |
| provider call-count / route audit를 payload metadata에 남김 | 중복 호출 여부 검증 가능 | metadata only이면 낮음 |

가장 안전한 첫 구현 단위는 최적화가 아니라 **timing trace**다. 이것은 provider route, elapsed_ms, status, selected_attempt, freshness_status만 기록하고 source data 선택에는 영향을 주지 않아야 한다.

## 11. REQUIRES_PARITY_PROOF 후보

| 후보 | 이유 |
|---|---|
| FRED series를 multi-id request로 묶기 | provider는 같지만 query shape와 CSV schema가 바뀐다 |
| FRED/Yahoo source 병렬 fetch | 결과 ordering, exception handling, Streamlit cache/thread safety 확인 필요 |
| source별 cache layer 추가 | cache key, freshness, bypass, stale 처리 parity 필요 |
| retry 결과 reuse | NORMAL/BYPASS 선택 규칙과 stale 방어 contract 검증 필요 |
| selected 후보의 required source만 fetch | 상단 요약/Final9 전체 상태가 달라질 수 있음 |
| summary-only payload와 selected detail payload 분리 | 과거 `5cc4e0c`에서 Cloud crash가 있었으므로 payload shape parity 필요 |

## 12. UNSAFE / DO NOT TOUCH

| 항목 | 이유 |
|---|---|
| FRED timeout 20초 단축 | 기존 성공 가능성 저하 |
| retry/BYPASS 제거 | stale 회복 계약 변경 |
| provider 우선순위 변경 | source semantics 변경 |
| provider 제거/교체 | 모델 입력 의미 변경 |
| TTL 변경 | freshness 의미 변경 가능 |
| 데이터 기간 축소 | rolling/EMA/threshold 결과 변경 가능 |
| candidate 계산 생략 | Final9/표/차트 coverage 변경 |
| stale 데이터를 정상 fresh로 처리 | 운영 판단 왜곡 |
| missing을 Risk-on/Risk-off로 해석 | 신호 의미 훼손 |

## 13. 병렬화 가능성

FRED/Yahoo source fetch들은 대부분 서로 독립적이다. 그러나 다음 관계가 있어 바로 SAFE로 보지 않는다.

- `us_10y_yield`는 HY/IG proxy와 10Y spread 계열 파생에 함께 쓰인다.
- `vix`는 VIX level, VIX spread, credit stress에 함께 쓰인다.
- provider fetch는 독립이어도 `build_transformed_frame` 이후 파생 계산은 source 전체가 모인 뒤 수행된다.
- 병렬화는 exception ordering, selected_attempt 기록, source_rows 순서, Streamlit Cloud thread safety, yfinance thread behavior를 검증해야 한다.

따라서 병렬 fetch는 `REQUIRES_PARITY_PROOF`다.

## 14. Before/After 100% Parity Contract

향후 최적화 구현 전후 다음은 동일해야 한다.

### Source parity

- provider
- provider_series_id
- query argument
- cache_mode
- selected_route 의미
- raw valid rows
- `observation_date`
- source value/OHLC
- selected_attempt
- final freshness status

### Aligned data parity

- `build_transformed_frame` output row count
- `date`
- all transformed columns
- `latest_available`
- lag / availability alignment
- KRX calendar alignment

### Signal parity

- Core15 component `risk_state`
- `valid_signal`
- `risk_start_signal`
- `risk_end_signal`

### Model parity

- child Combo1 `raw_risk_state`
- Final9 `raw_risk_state`
- Final9 `t1_position`
- `active_count`
- K/L
- basis date

### UI data parity

- group summary
- current status panel
- component status table
- benchmark close history
- candidate signal history
- component signal history
- chart underlying DataFrame

## 15. 향후 구현 전 필수 테스트

1. cold cache provider fetch parity
2. warm cache provider fetch parity
3. provider success path
4. primary NORMAL stale + BYPASS fresh path
5. NORMAL fresh -> BYPASS not executed
6. provider timeout/fetch failure -> error status preserved
7. all provider failure for a source -> no missing-as-risk-on
8. FRED request argument equality
9. Yahoo request argument equality
10. provider call count assertion
11. source raw DataFrame exact parity
12. transformed source exact parity
13. Core15 exact signal parity
14. child Combo1 exact parity
15. Final9 exact parity
16. chart underlying DataFrame parity
17. selected candidate switch parity
18. repeated Streamlit rerun cache hit/miss parity
19. Cloud-like old payload shape defense
20. timing trace does not change payload semantic hash

## 16. 가장 안전한 다음 구현 단위

바로 최적화하지 말고, 먼저 provider timing trace를 추가하는 것이 맞다.

권장 최소 구현:

- `fetch_with_optional_bypass` 또는 caller에서 source별 elapsed time 기록
- NORMAL/BYPASS attempt별 elapsed time 기록
- provider, series, route, cache_mode, status, freshness_status, row_count 기록
- 결과 선택 로직은 변경하지 않음
- UI에는 노출하지 않고 debug/report용 metadata만 보존
- 최적화 전/후 semantic payload hash는 동일해야 함

이 trace가 PASS하면 다음 후보는 FRED session reuse다. 병렬화나 multi-id FRED batch는 그 다음 단계다.

## 17. 코드 수정 없이 확정 가능한 내용 / 추가 측정 필요 내용

확정 가능:

- Macro5 live payload cache miss 시 11개 source 전체 fetch.
- 9개 FRED source는 순차 HTTP request.
- FRED request timeout은 20초.
- stale일 때만 source별 BYPASS 1회가 추가된다.
- timeout/fetch failure는 BYPASS retry 대상이 아니다.
- 일반 page render는 cloud probe route를 호출하지 않는다.

추가 runtime timing trace 필요:

- 실제 23초를 만든 provider id.
- NORMAL과 BYPASS 중 어느 쪽이 느린지.
- FRED timeout인지 Yahoo/yfinance 지연인지.
- cache miss에서만 생기는지.
- Cloud 환경에서 특정 FRED series가 반복적으로 느린지.
- post-fetch 계산 시간이 의미 있게 큰지.

## 18. 최종 질문 답변

1. **23초의 가장 큰 원인은 무엇인가?**  
   코드상 가장 유력한 원인은 FRED 9개 순차 요청 중 1개가 `timeout=20`에 근접하는 경우다. 실측 trace 없이는 provider id를 확정하지 않는다.

2. **순수 중복 작업이 존재하는가?**  
   한 payload run 안에서 같은 source를 반복 fetch하는 명확한 중복은 확인되지 않았다. 다만 FRED 9개 개별 순차 요청은 최적화 여지가 있다.

3. **데이터 계약을 전혀 바꾸지 않고 줄일 수 있는 시간이 있는가?**  
   가능성은 있다. FRED session reuse는 낮은 위험 후보이고, 병렬 fetch/multi-id batch는 parity proof가 필요하다.

4. **가장 안전한 첫 번째 최적화 후보는 무엇인가?**  
   최적화가 아니라 provider timing trace 추가가 먼저다. 그 다음 FRED session reuse.

5. **예상 위험은 무엇인가?**  
   timeout/retry/fallback/freshness/cache를 잘못 건드리면 최신성, stale 방어, candidate basis date, Final9 state가 달라질 수 있다.

6. **구현 전에 어떤 parity test가 반드시 필요한가?**  
   source raw, transformed source, Core15, child Combo1, Final9, UI/chart payload exact parity와 provider call count assertion.

7. **바로 구현 단계로 넘어가도 되는가?**  
   바로 성능 최적화는 권장하지 않는다. 먼저 timing trace 단계로 넘어가는 것은 적절하다.

## 19. 작업 범위 확인

- 기존 코드 수정 없음
- 기존 테스트 수정 없음
- 기존 asset/config 수정 없음
- pytest 실행 없음
- Streamlit 실행 없음
- provider 실제 호출 없음
- git fetch/pull 없음
- commit/push/deploy 없음

