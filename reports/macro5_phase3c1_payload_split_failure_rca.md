# Macro5 Phase 3-C1 Payload Split Failure RCA

## Gate

`PASS_PHASE3C1_FAILURE_RCA_COMPLETE`

범위:

- Read-only RCA 중심으로 수행했다.
- 기존 코드, 테스트, asset, report는 수정하지 않았다.
- 신규 작성 파일은 이 보고서 1개뿐이다.
- pytest, Streamlit app, runtime script는 실행하지 않았다.
- git fetch / pull 등 remote ref를 변경하는 명령은 실행하지 않았다.

제약:

- Streamlit Cloud의 실제 traceback 전문은 제공되지 않았다.
- 따라서 정확한 런타임 분기는 코드 diff, 현재 안정 코드, 증상 문구를 근거로 재구성했다.

## 기준 상태

현재 로컬 기준:

- branch: `main`
- HEAD: `d0aba7e410463e217416457689d895a89900fdd9`
- origin/main: `d0aba7e410463e217416457689d895a89900fdd9`
- working tree: clean

관련 commit:

- 안정 기준: `adbf077 Cache Macro5 detail charts selectively`
- 문제 commit: `5cc4e0c Split Macro5 summary and selected detail payload`
- rollback: `d385b8e Revert "Split Macro5 summary and selected detail payload"`
- 현재 최신: `d0aba7e Allow Macro5 KOSPI live partial daily row`

`5cc4e0c` 변경 파일:

- `kospi_macro5_runtime/page_adapter.py`
- `technical_signal_dashboard.py`
- `tests/test_kospi_macro5_d1c3a2_latest_history.py`
- `tests/test_kospi_macro5_d1c3b3r_chart_regression.py`
- `tests/test_macro5_phase3c1_selected_detail_payload.py`
- `reports/macro5_phase3c1_selected_detail_payload_report.md`

`d385b8e`는 위 변경 범위를 되돌렸다.

## 실패 증상

운영 Streamlit Cloud에서 관찰된 증상:

- `Live history unavailable`
- 최신 대표 차트를 표시할 수 없음
- component detail history가 정상 준비되지 않은 상태에서 `DataFrame.groupby("component_id")` 실행
- `KeyError`
- Macro5 페이지 전체 crash

## 핵심 원인

문제 commit `5cc4e0c`는 Macro5 live payload에서 기존 full component history를 제거하고, 선택 후보 1개에 대해서만 detail history를 나중에 재구성하는 구조로 바꿨다.

기존 안정 구조:

```text
live payload
├─ candidate_signal_history
├─ component_signal_history   전체 Final9 component detail
└─ benchmark_close_history

page render
→ full component history 존재 확인
→ 선택 후보 slice
→ chart/detail render
```

문제 commit 구조:

```text
live payload
├─ candidate_signal_history
├─ component_signal_history_mode = selected_detail_only
├─ core15_component_history
├─ child_combo1_history
└─ benchmark_close_history

page render
→ candidate/benchmark만 있으면 live history ready로 판단
→ 선택 후보 component detail을 별도 helper로 재구성
→ chart/detail render
```

이 변경에서 readiness 계약이 깨졌다.

`_live_history_ready5k`가 더 이상 component detail 준비 여부를 포함하지 않게 되었고, 이후 차트 렌더링은 여전히 `_candidate_components5k.groupby("component_id", sort=False)`를 전제로 했다.

즉 `live history ready`라는 이름은 유지됐지만 실제 의미는:

```text
candidate history + benchmark history ready
```

로 축소되었다. 반면 하위 UI는 여전히:

```text
candidate history + benchmark history + selected component detail with component_id schema ready
```

를 요구했다.

## 직접적인 취약 지점

문제 commit의 `technical_signal_dashboard.py` 흐름:

1. `_live_history_ready5k`에서 `_live_component_history_all5k` 조건 제거
2. `_live_component_history_all5k`가 없으면 `build_selected_component_signal_history(...)` 호출
3. helper 실패 시 `_live_error5k`만 기록
4. `_live_selected_ok5k`는 component detail이 비어 있지 않은지만 확인
5. 차트 하단에서 `_candidate_components5k.groupby("component_id", sort=False)` 실행

문제는 "비어 있지 않음"과 "렌더링에 필요한 schema가 있음"이 같지 않다는 점이다.

필수 schema:

- `parent_candidate_id`
- `component_id`
- `date`
- `component_risk_state`
- `component_label`
- `component_K`
- `component_L`
- `valid_signal`

`component_id`가 없는 DataFrame이 전달되면 groupby에서 즉시 `KeyError`가 발생한다.

## 왜 full payload 제거가 위험했나

기존 full `component_signal_history`는 여러 UI가 암묵적으로 공유하던 계약이었다.

사용 위치:

- 현재 상태 summary의 active component label
- 지표별 상태 보기
- 대표 chart 하단 component chart 반복 렌더
- Combo1 component raw/EMA/threshold chart context
- Combo2 child Combo1 detail display
- chart regression tests

`5cc4e0c`는 이 full payload를 제거했지만, 모든 소비 지점을 새 selected-detail 계약으로 완전히 분리하지 못했다.

특히 "summary-only payload"와 "selected detail payload"의 경계가 명확하지 않았다.

필요했던 분리:

```text
live_summary_ready
selected_component_detail_ready
chart_ready
component_status_ready
```

실제 변경:

```text
_live_history_ready5k
```

하나에 여러 의미가 섞여 있었다.

## page_adapter 변경의 위험

`page_adapter.py`의 문제 commit 변경:

- payload에서 `"component_signal_history"` 제거
- `"component_signal_history_mode": "selected_detail_only"` 추가
- `build_selected_component_signal_history(live_payload, candidate_id)` 추가
- `_component_signal_history(..., candidate_ids=[...])` 선택 필터 추가

helper 자체의 방향은 성능 최적화 관점에서 타당하지만, 다음 방어가 부족했다.

- 선택 detail 결과 schema 검증 없음
- helper 실패 시 UI 계약 수준의 fallback 없음
- selected detail이 empty/frozen-only/live-tail-missing일 때 chart 소비자별 동작 검증 부족
- Streamlit Cloud 환경의 parquet filter / cache / asset packaging 차이 검증 부족

## 왜 테스트가 놓쳤나

문제 commit에서 추가된 테스트는 주로 helper의 성공 경로를 확인했다.

확인한 것:

- selected component history가 full slice와 일치하는지
- selected detail helper가 source fetch나 live tree recompute를 하지 않는지
- chart regression test가 helper를 통해 component history를 가져올 수 있는지

놓친 것:

- Streamlit page render 전체 경로
- `_live_history_ready5k=True`지만 selected component detail이 없거나 schema가 깨지는 경우
- `build_selected_component_signal_history` 예외 발생 후 UI fallback
- empty DataFrame이지만 필요한 column이 없는 경우
- `component_id` missing schema로 groupby가 실패하는 경우
- Cloud cache hit/miss 조합
- old cached payload와 new render code의 혼재 가능성
- 선택 후보 변경 시 helper가 매번 안정적으로 schema를 제공하는지
- chart/detail/status 각각의 readiness가 분리되어 있는지

테스트가 helper를 직접 호출했기 때문에, 실제 Streamlit page에서 발생하는 "payload 준비 상태와 render branch의 불일치"를 잡지 못했다.

## Cloud에서 더 잘 터질 수 있는 조건

Cloud-only 또는 Cloud에서 더 노출되기 쉬운 조건:

- Streamlit cache에 이전 payload shape이 남아 있는 경우
- live source 일부 실패로 `core15_component_history` 또는 `child_combo1_history`가 비어 있는 경우
- parquet filter engine 동작 차이
- asset 파일은 있으나 선택 후보 필터 결과가 비어 있는 경우
- session_state의 선택 후보가 초기화 직후 바뀌는 경우
- candidate/benchmark는 준비됐지만 component detail은 아직 준비되지 않은 중간 상태

이 조건에서는 full payload 방식보다 selected-detail 방식이 readiness 오류에 더 취약하다.

## Rollback 판단

rollback은 적절했다.

이유:

- 운영 Macro5 페이지 전체 crash였고, hotfix guard로 덮기보다 직전 안정 계약으로 되돌리는 것이 안전했다.
- 문제 commit은 성능 최적화 구조 변경이었고, 기능 필수 변경이 아니었다.
- full component payload 계약은 직전 안정 버전에서 이미 운영 검증된 경로였다.
- `d385b8e`가 문제 commit의 변경 범위만 되돌렸다.

## 재시도 원칙

Phase 3-C1을 재시도한다면 "full payload 제거"부터 하지 않는다.

권장 순서:

1. full `component_signal_history`는 유지한다.
2. selected detail helper를 병렬로 추가한다.
3. 모든 Final9 후보에 대해 selected detail == full slice parity를 검증한다.
4. page render에서 selected detail을 opt-in으로 사용하되 full payload fallback을 유지한다.
5. readiness 변수를 분리한다.
6. selected detail result에 schema validator를 둔다.
7. Cloud-like payload shape 테스트를 추가한다.
8. 충분히 검증된 뒤 마지막 단계에서만 full payload 제거를 검토한다.

필수 readiness:

```text
live_summary_ready
candidate_history_ready
benchmark_history_ready
selected_component_detail_ready
chart_ready
component_status_ready
```

필수 hard contract:

```text
if chart_ready:
    candidate history has required columns
    benchmark history has required columns
    selected component detail has required columns
    selected component detail parent_candidate_id == selected candidate
    selected component detail date covers chart basis date
```

## 재시도 전 필수 테스트

재시도 전 최소 테스트:

- Final9 9개 전 후보 selected detail vs full component slice parity
- Combo1 후보 selected detail parity
- Combo2 후보 selected detail parity
- selected helper exception 시 page가 crash하지 않고 stable frozen path로 fallback
- selected helper empty result 시 chart/detail 미표시 또는 stable fallback
- selected helper result에 `component_id` 누락 시 PASS 금지
- `_live_history_ready5k=True`, `_live_selected_ok5k=False` 분기 테스트
- chart groupby 직전 schema check
- old payload shape와 new payload shape compatibility test
- Streamlit route 함수 수준의 Macro5 render smoke
- Cloud asset missing / parquet filter fallback test

중요:

- 테스트는 helper 단독 성공 경로가 아니라 page render branch를 검증해야 한다.
- KeyError guard만 추가하는 것은 충분하지 않다.
- missing component detail을 Risk-on 또는 OFF로 해석하면 안 된다.

## 재시도 가능 여부

현재 즉시 재시도는 권장하지 않는다.

먼저 필요한 작업:

1. selected detail schema contract 정의
2. readiness 변수 분리
3. full payload fallback 유지
4. page-level render tests 추가
5. Cloud-like cache/payload shape tests 추가

그 뒤 작은 단계로 다시 시도하는 것이 맞다.

## 결론

`5cc4e0c`의 실패는 단순한 `groupby` 방어코드 누락이 아니라, payload split 과정에서 live readiness 계약과 component detail 소비 계약이 서로 어긋난 것이 핵심이다.

직전 안정 구조는 full component history를 payload에 포함했기 때문에 Macro5 chart/detail/status가 같은 schema를 공유했다.

문제 commit은 full history를 제거하고 selected detail을 지연 생성하도록 바꿨지만, page render 경로는 여전히 component detail이 준비되어 있고 `component_id` schema가 존재한다는 전제를 유지했다.

따라서 다음 재시도는 "더 작은 payload"보다 먼저 "명시적 readiness + schema contract + full fallback parity"를 닫아야 한다.
