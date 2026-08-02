# KOSPI Macro5 D1-C3B.1 UI Parity Read-Only Audit

## 1. Executive Conclusion

Gate: `PASS_KOSPI_MACRO5_D1C3B1_UI_PARITY_READ_ONLY_AUDIT_COMPLETE`

이번 감사는 visible 매크로 지표 4(internal `macro6`)를 UI 기준으로 두고 visible 매크로 지표 5(internal `macro5_kospi`)를 읽기 전용으로 비교했다. 계산식, 신호, 후보, availability, freshness, runtime, page adapter, Streamlit UI 코드는 수정하지 않았다.

핵심 결론은 다음과 같다.

- Macro5는 Live Shadow 계산과 최신 tail 표시 연결은 되어 있으나, Macro4와 UI 구조 parity는 아직 맞지 않는다.
- 가장 큰 차이는 상단 상태 영역, 백테스트 비교표 분리, 지표별 상태표, 컴포넌트 차트의 데이터 series 구성이다.
- Macro5의 현재 데이터 반환 구조는 Final9/Child Combo1/Core15 risk state, active count, T+1, source freshness, KOSPI close는 제공하지만, Macro4식 raw/EMA/threshold 보조선 차트는 추가 page adapter 배선이 필요하다.
- 다음 수정은 B1(UI 구조/표) -> B2(차트 표시) -> B3(시각 회귀) 순서가 안전하다.

## 2. 기준 Commit과 Git 상태

| 항목 | 값 |
|---|---|
| 작업 경로 | `/tmp/technical-signal-dashboard-d1c3a1-20260802_195851` |
| 기준 프로젝트 | `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard` |
| 현재 branch | detached HEAD |
| HEAD | `4fe4fb9982bc28eb136d25d0980b28cbb1f085b1` |
| 최근 commit | `4fe4fb9 Connect KOSPI Macro5 live history` |
| 감사 전 git status | clean |
| D1-C3A.1 report | `reports/kospi_macro5_d1c3a1_result.md` 존재 |
| D1-C3A.2 report | `reports/kospi_macro5_d1c3a2_result.md` 존재 |

## 3. Render 호출 구조

### Macro4 visible "매크로 지표 4" / internal `macro6`

| 단계 | 함수/위치 | 확인 내용 |
|---|---|---|
| Route | `main()` / `technical_signal_dashboard.py:16111-16112` | `market_macro`의 `macro6` 탭에서 `render_macro6_proxy_final_section` 호출 |
| Section render | `render_macro6_proxy_final_section` / `15114-15455` | Macro4 전체 UI 본문 |
| Preset loader | `_load_macro6_proxy_final_presets` / `7290-7420` | Combo2 + Combo1 후보 로드 |
| Runtime snapshot | `_compute_macro6_operating_snapshot` / `8441-8442` | 후보별 현재 신호 계산 |
| Top summary | `_macro3_group_availability_html`, `_macro6_group_consensus_html` / `15174-15219` | 계산 가능 수와 Risk-off 수 |
| Controls | `15236-15318` | 프리셋, 기준지수, 기간, 보조선, 조합지표, K/L |
| Current state | `_build_macro6_status_panel` / `8707-8824`, `15377-15389` | 기준일, 현재 플래그, 상태, 실행 안내 |
| Duration | `_macro6_state_duration_html` / `8956-8977`, `15390-15392` | 현재 상태 시작일과 지속 거래일 |
| Backtest tables | `_build_macro6_backtest_panel` / `9026-9120`, `15394-15415` | 조합2/조합1 비교표 분리 |
| Detail status | `_build_macro6_status_panel` table / `15417-15424` | 현재 선택 후보의 구성지표 상태 |
| Main chart | `_make_macro6_combo_chart_from_snapshot` / `8334-8395`, `15426-15432` | 대표 Risk cycle 차트 |
| Component charts | `_build_macro6_component_chart` / `9418-9484`, `_build_macro6_indicator_chart` / `9305-9415`, `15433-15447` | 구성지표 차트 |

### Macro5 visible "매크로 지표 5" / internal `macro5_kospi`

| 단계 | 함수/위치 | 확인 내용 |
|---|---|---|
| Route | `main()` / `technical_signal_dashboard.py:16095-16097` | `market_macro`의 `macro5_kospi` 탭에서 `render_macro5_kospi_section` 호출 |
| Section render | `render_macro5_kospi_section` / `14494-14826` | Macro5 전체 UI 본문 |
| Frozen assets | `14499-14552` | Final9 manifest, metrics, reference signals, component dictionary 로드 |
| Live page data | `_load_macro5_kospi_live_page_data_cached` -> `load_macro5_live_page_data` / `14555-14561`, `page_adapter.py:24-117` | Live source, transformed source, Core15, Child Combo1, Final9 계산 |
| Controls | `14565-14633` | 프리셋, 기준지수, 기간, 원본선, 조합지표, K/L |
| Current state cards | `14635-14696` | Live 기준일, 후보 구분, Raw/T+1, Active Count 등 8개 카드 |
| Frozen metric cards | `14698-14714` | 선택 후보 Frozen 성과 요약 |
| Backtest table | `14716-14723` | 단일 `st.dataframe` 비교표 |
| Detail status | `14725-14759` | Final9 후보 snapshot 중심 상태표 |
| Main chart | `_macro5_kospi_build_main_chart` / `13017-13077`, `14776-14792` | KOSPI + Final9 raw/T+1 차트 |
| Component charts | `_macro5_kospi_build_component_chart` / `13080-13122`, `14801-14820` | KOSPI + component ON marker 차트 |
| Advanced/meta | `14794-14799` | Final9 Frozen 후보 상세 expander |

## 4. 화면 섹션 1:1 매핑

| 순서 | Macro4 영역 | Macro4 함수 | Macro5 대응 영역 | Macro5 함수 | 상태 | 차이 | 수정 예상 범위 |
|---:|---|---|---|---|---|---|---|
| 1 | 페이지 설명 | `render_macro6_proxy_final_section` | 페이지 설명 | `render_macro5_kospi_section` | DIFFERENT_CONTENT | Macro5는 Frozen/Live Shadow 설명이 길고 Macro4보다 기술적 | B1 |
| 2 | 계산 가능 요약 | `_macro3_group_availability_html` | 없음, 후보 구분 카드 일부 | 직접 카드 HTML | MISSING_IN_MACRO5 | Combo1/Combo2 계산 가능/불가 요약 없음 | B1 |
| 3 | Risk-off 요약 | `_macro6_group_consensus_html` | 없음, 선택 후보 상태 카드만 있음 | 직접 카드 HTML | MISSING_IN_MACRO5 | Combo1/Combo2 그룹별 Risk-off 수 없음 | B1 + UI_DATA_WIRING_REQUIRED |
| 4 | 조합 프리셋 | `st.selectbox` | 조합 프리셋 | `st.selectbox` | DIFFERENT_CONTENT | Macro4는 Combo2/Combo1 구분 separator, Macro5는 Final9 단일 목록 | B1 |
| 5 | 기준지수 | disabled selectbox S&P500 | disabled selectbox KOSPI | same pattern | SAME | 시장명만 다름 | B1 minimal |
| 6 | 기간 선택 | `st.select_slider` | `st.select_slider` | same pattern | SAME | 옵션 동일 | B3 확인 |
| 7 | 보조선 표시 | `macro6_show_raw` | `macro5_kospi_show_raw` | checkbox | DIFFERENT_CONTENT | Macro5는 원본선 표시지만 component chart에서 실질 보조선 미표시 | B2 + UI_DATA_WIRING_REQUIRED |
| 8 | 조합 지표 선택 | disabled multiselect | disabled multiselect | same pattern | DIFFERENT_CONTENT | Macro5 label이 내부 ID/suffix 중심 | B1 |
| 9 | 리스크 기준 | K/L 한글 문구 | K/L 한글 문구 | 직접 HTML | DIFFERENT_CONTENT | Macro4는 "시작 N개 이상 ON / 종료 N개 이하 ON", Macro5는 "진입 K / 종료 L" | B1 |
| 10 | 현재 상태 요약 | `_build_macro6_status_panel` summary | 8개 카드 | 직접 카드 HTML | DIFFERENT_STRUCTURE | Macro4 한 줄 요약 vs Macro5 카드 grid, 좁은 화면에서 세로 깨짐 가능 | B1 |
| 11 | 상태 시작/지속 | `_macro6_state_duration_html` | 지속 거래일 카드만 있음 | 직접 카드 HTML | DIFFERENT_CONTENT | Macro5 상태 시작일이 카드에 없음 | B1 + UI_DATA_WIRING_REQUIRED |
| 12 | 조합2 백테스트 비교 | `_build_macro6_backtest_panel` | 단일 비교표 | `st.dataframe` | MISSING_IN_MACRO5 | 조합2 별도 expander 없음 | B1 |
| 13 | 조합1 백테스트 비교 | `_build_macro6_backtest_panel` | 단일 비교표 | `st.dataframe` | MISSING_IN_MACRO5 | 조합1 별도 expander 없음 | B1 |
| 14 | 지표별 상태 보기 | `_build_macro6_status_panel` table | Final9 snapshot table | `st.dataframe` | DIFFERENT_STRUCTURE | Macro4는 선택 후보 구성지표, Macro5는 전체 Final9 후보/기술 상태 중심 | B1 + UI_DATA_WIRING_REQUIRED |
| 15 | 대표 상태 차트 | `_make_macro6_combo_chart_from_snapshot` | `_macro5_kospi_build_main_chart` | Plotly | DIFFERENT_CONTENT | Macro5는 KOSPI/raw/T+1 중심, Macro4와 marker/label/summary 차이 | B2 |
| 16 | 구성지표 상세 차트 | `_build_macro6_component_chart`, `_build_macro6_indicator_chart` | `_macro5_kospi_build_component_chart` | Plotly | DIFFERENT_CONTENT | Macro5 component chart는 KOSPI + ON marker만 표시 | B2 + UI_DATA_WIRING_REQUIRED |
| 17 | 고급 설정 | 없음 또는 caption 중심 | "고급 설정: Final9 Frozen 후보 상세" | `st.expander` | EXTRA_IN_MACRO5 | 일반 화면에 내부 technical table 노출 | B1 |
| 18 | 기술 메타데이터 | 표 내부 candidate key 일부 | reference/source/hash성 컬럼 노출 | `st.dataframe`, caption | EXTRA_IN_MACRO5 | 일반 사용 화면에서 내부 parity/source label 과노출 | B1 |

Mapping count: 18

## 5. 상단 상태 영역 차이

| 점검 항목 | Macro4 | Macro5 | 상태 |
|---|---|---|---|
| 계산 가능 수 | Combo2/Combo1 각각 표시 | 없음 | MISSING_IN_MACRO5 |
| 계산 불가 수 | Combo2/Combo1 각각 표시 | 없음 | MISSING_IN_MACRO5 |
| Risk-off 개수 | Combo2/Combo1 각각 표시 | 선택 후보 Raw 상태만 표시 | MISSING_IN_MACRO5 |
| 기준일 | 한 줄 요약의 `기준일` | 카드의 `Live 기준일` | DIFFERENT_STRUCTURE |
| 현재 플래그 | `N / 전체 ON (활성 지표명)` | `Active Count N / 전체` | DIFFERENT_CONTENT |
| 상태 ON/OFF | `리스크 사이클 ON/OFF` | `Raw 상태`, `T+1 적용 상태` 분리 | DIFFERENT_CONTENT |
| 실행 안내 | 신규 시작/종료 및 T+1 안내 | 없음 | MISSING_IN_MACRO5 |
| 상태 시작일 | 별도 duration HTML | 없음 | MISSING_IN_MACRO5 |
| 지속 거래일 | duration HTML | 카드에 표시 | DIFFERENT_STRUCTURE |
| 배치 | compact helper text | 8개 card grid | DIFFERENT_STYLE |
| 깨진 세로 출력 가능성 | 낮음 | card grid가 화면 폭 부족 시 세로로 길어짐 | REVIEW_REQUIRED |

코드 관점 원인: Macro5는 `macro2-card-grid`에 8개 카드를 일괄 렌더링한다(`14677-14691`). Macro4는 `_build_macro6_status_panel`에서 flex 한 줄 요약 HTML을 만든다(`8782-8789`). 따라서 세로로 깨지는 문제는 계산 문제가 아니라 레이아웃/표현 방식 차이다.

## 6. 백테스트 비교 영역 차이

| 항목 | Macro4 | Macro5 | 상태 |
|---|---|---|---|
| Expander 분리 | `백테스트 비교 보기 · 조합2`, `백테스트 비교 보기 · 조합1` | `백테스트 비교 보기` 하나 | DIFFERENT_STRUCTURE |
| 기본 펼침 | 둘 다 `expanded=False` | `expanded=False` | SAME |
| 구현 방식 | HTML table + inline style | `st.dataframe` | DIFFERENT_STYLE |
| 선택 후보 강조 | row background/border | 없음 | MISSING_IN_MACRO5 |
| 컬럼 | 역할/후보, 10Y 자산, 20Y 자산, 20Y CAGR, 10Y MDD, 20Y MDD, 20Y Risk-off, 20Y Cycle, 짧은 Cycle, 현재 | slot, model_type, role, suffix, m_or_n, K, L, cagr, mdd, calmar, risk_off_ratio, annual_turnover, source_signal_parity | DIFFERENT_CONTENT |
| B&H 대비 배수 | asset/MDD ratio span | 없음 | MISSING_IN_MACRO5 |
| 현재 상태 표시 | 현재 Risk-off ratio chip | 없음 | MISSING_IN_MACRO5 |
| 내부 ID 노출 | candidate key 일부만 작은 글자 | suffix/source parity 등 기술 필드 노출 | EXTRA_IN_MACRO5 |

Macro5는 KOSPI Final9가 Combo1 4개 + Combo2 5개라서 그룹별 분리 표를 만들 데이터는 `model_type`으로 가능하다. 단 Macro4와 같은 10Y/20Y 자산 컬럼은 현재 `kospi_final9_candidate_metrics.csv`에 없고 `cagr/mdd/calmar` 중심이므로, 완전 동일 컬럼은 `UI_DATA_WIRING_REQUIRED` 또는 KOSPI용 대응 컬럼 합의가 필요하다.

## 7. 지표별 상세보기 차이

| 항목 | Macro4 | Macro5 | 상태 |
|---|---|---|---|
| 표시 대상 | 현재 선택 후보의 구성지표 | 전체 Final9 snapshot 일부 | DIFFERENT_STRUCTURE |
| 1열/2열 compact table | 있음 | 없음, dataframe | DIFFERENT_STYLE |
| 선택 여부 | 원형 표시 | 없음 | MISSING_IN_MACRO5 |
| 현재 플래그 | 원형 표시 | Raw/T+1/active count 중심 | DIFFERENT_CONTENT |
| 최신 사용값 | 지표별 latest text | source_rows 별도 존재하나 상태표에 미연결 | UI_DATA_WIRING_REQUIRED |
| 원천 관측일/사용가능일/지연일 | Macro6 row에서 계산 | page adapter `source_rows`에 있음 | AVAILABLE_ALREADY |
| source/fallback label | Macro6 latest text 일부 | source_rows/provider/route 있음 | AVAILABLE_ALREADY |
| 내부 component ID 노출 | 낮음 | component_id/candidate_id 노출 가능 | EXTRA_IN_MACRO5 |

Macro5의 `page_adapter.py`는 `source_rows`, `candidate_rows`, `core15_component_history`, `child_combo1_history`, `component_signal_history`를 반환한다(`page_adapter.py:102-114`). 따라서 선택 후보의 구성요소별 ON/OFF, active count, source freshness는 만들 수 있으나, Macro4식 한글 label과 최신 사용값 row로 조립하는 UI 배선이 아직 부족하다.

## 8. 차트 크기·축·내용 차이

### 대표 차트

| 항목 | Macro4 | Macro5 | 상태 |
|---|---|---|---|
| Builder | `_make_macro6_combo_chart_from_snapshot` | `_macro5_kospi_build_main_chart` | DIFFERENT_CONTENT |
| Input | snapshot event frame + S&P series | candidate_signal_history + benchmark_close_history | SAME concept |
| X column | date/index | date | SAME |
| Left Y | S&P500 | KOSPI | SAME concept |
| Risk background | `_add_macro_combo_risk_cycle_background` | 같은 helper 사용 | SAME |
| Event markers | 리스크 시작/종료 | Raw Risk 시작/종료 | DIFFERENT_CONTENT |
| Height | Macro6 chart helper 기준, 대표 차트는 `_make_macro6_combo_chart_from_snapshot` 설정 확인 필요 | 430 | REVIEW_REQUIRED |
| Margin | Macro4 helper `_ml`/chart setting | `l=8,r=8,t=34,b=8` | REVIEW_REQUIRED |
| Legend | Macro4 chart helper 설정 | horizontal, top-right | REVIEW_REQUIRED |
| T+1 line | 없음 또는 별도 표시 없음 | show_raw일 때 `T+1 투자 가능` line | EXTRA_IN_MACRO5 |

### 구성지표 / component 차트

| 항목 | Macro4 Combo1 지표 차트 | Macro4 Combo2 component 차트 | Macro5 component 차트 | 상태 |
|---|---|---|---|---|
| Builder | `_build_macro6_indicator_chart` | `_build_macro6_component_chart` | `_macro5_kospi_build_component_chart` | DIFFERENT_CONTENT |
| 지표 raw value | 있음 | Child Combo1 차트는 price/state 중심 | 없음 | UI_DATA_WIRING_REQUIRED |
| EMA/보조선 | 있음 | 없음 | 없음 | UI_DATA_WIRING_REQUIRED |
| 시작/종료 기준선 | 있음 | 없음 | 없음 | UI_DATA_WIRING_REQUIRED |
| Benchmark overlay | non-Index는 secondary y-axis | S&P price left y | KOSPI only left y | DIFFERENT_STRUCTURE |
| Secondary y-axis | indicator chart에서 사용 | 없음 | 없음 | UI_DATA_WIRING_REQUIRED |
| Risk background | component state 기준 | component state 기준 | component state 기준 | SAME |
| Event markers | 시작/종료 triangle | component 시작/종료 triangle | component ON square only | DIFFERENT_CONTENT |
| Height | indicator 300, component 260 | component 260 | 300 | DIFFERENT_STYLE |
| Expander default | Combo2 구성요소는 expanded=True | Combo2 구성요소는 expanded=True | 전부 expanded=False | DIFFERENT_STRUCTURE |

Macro5의 component chart는 `component_risk_state`를 `fillna(0)`으로 시각화용 bool로 바꾸고 KOSPI 위에 ON marker만 그린다(`13080-13122`). D1-C3A.2에서 결측 처리 계산 경계는 보강됐지만, UI 차트에서는 유효/결측 구간 표시가 별도 없음. 이는 B2에서 "시각 표시"만 조정할 항목이다.

## 9. Expander 기본 상태 차이

| Expander | Macro4 | Macro5 | 상태 |
|---|---|---|---|
| 백테스트 비교 보기 · 조합2 | `expanded=False` | 없음 | MISSING_IN_MACRO5 |
| 백테스트 비교 보기 · 조합1 | `expanded=False` | 없음 | MISSING_IN_MACRO5 |
| 백테스트 비교 보기 | 없음 | `expanded=False` | EXTRA_IN_MACRO5 |
| 지표별 상태 보기 | `expanded=False` | `expanded=False` | SAME label / DIFFERENT_CONTENT |
| 구성지표 상세 차트 | Combo2 구성요소는 `expanded=True`, Combo1 선택지표는 True | 전부 `expanded=False` | DIFFERENT_STRUCTURE |
| 고급 설정 | 없음 | `expanded=False` | EXTRA_IN_MACRO5 |

## 10. UI 데이터 준비 상태

| 데이터 항목 | 현재 상태 | 근거/메모 |
|---|---|---|
| 지표 raw value | AVAILABLE_IN_RUNTIME_NOT_PAGE_ADAPTER / REVIEW_REQUIRED | `core15.py` 계산 함수는 `value`, `close`, `rsi`, `bb_*` 등을 만들지만 `page_adapter._core15_component_history`는 risk/event/status 컬럼만 반환 |
| EMA/보조선 | AVAILABLE_IN_RUNTIME_NOT_PAGE_ADAPTER | `compute_dynamic_quantile_signal_frame`은 `ema*`, `risk_start_line`, `risk_end_line` 생성 |
| 시작 기준선 | AVAILABLE_IN_RUNTIME_NOT_PAGE_ADAPTER | Core15 frame 내부에 존재 가능, page adapter 미노출 |
| 종료 기준선 | AVAILABLE_IN_RUNTIME_NOT_PAGE_ADAPTER | Core15 frame 내부에 존재 가능, page adapter 미노출 |
| component ON/OFF | AVAILABLE_ALREADY | `component_signal_history.component_risk_state` |
| Child Combo1 raw state | AVAILABLE_ALREADY | `child_combo1_history.raw_risk_state` |
| active count | AVAILABLE_ALREADY | `candidate_rows.active_count`, `child_combo1_history.active_count`, reference component active count 일부 |
| Final9 raw state | AVAILABLE_ALREADY | `candidate_signal_history.raw_risk_state` |
| Final9 T+1 | AVAILABLE_ALREADY | `candidate_signal_history.t1_position`, `candidate_rows.t1_position` |
| start/end events | AVAILABLE_ALREADY | `risk_start_signal`, `risk_end_signal` 및 chart event helper |
| KOSPI close | AVAILABLE_ALREADY | `benchmark_close_history.kospi_close` |
| source observation date | AVAILABLE_ALREADY | `source_rows.actual_latest_observation_date`, `raw_latest_observation_date` |
| availability date | AVAILABLE_ALREADY | `source_rows.actual_latest_available_date` |
| delay trading days | AVAILABLE_ALREADY | `source_rows.lag_krx_sessions` |
| source/fallback label | AVAILABLE_ALREADY | `source_rows.provider`, `selected_route`, `provider_series_id` |

UI_DATA_WIRING_REQUIRED count: 7

## 11. 기능 보호 경계

### UI 변경 가능 후보

- Streamlit layout
- HTML/CSS
- label
- expander 분리
- 표 컬럼 선택/표시 순서
- 후보 표시명
- 차트 height/margin
- 축 배치
- 범례
- 기존 데이터 series 표시
- expander 기본 펼침 여부
- page adapter의 표시용 컬럼 전달

### 변경 금지

- 모든 수식
- 모든 임계값
- 모든 상태 계산
- 후보 구성
- 데이터 정렬 계약
- availability/freshness
- missing 처리
- T+1
- hysteresis
- active count
- 이벤트 생성
- Frozen/Live 결합 계약
- source adapter
- retry/cache/probe

향후 UI 수정은 기존 결과 DataFrame의 표시 방식만 바꾸는 원칙을 유지해야 한다. raw/EMA/threshold가 필요하면 새 계산식 작성이 아니라 기존 Core15 runtime 결과를 페이지 표시용으로 전달해야 한다.

## 12. B1/B2/B3 수정 후보

### B1 - UI 구조/표

| ID | 항목 | 상태 | 권장 |
|---|---|---|---|
| B1-01 | 상단 계산 가능/불가 요약 복원 | MISSING_IN_MACRO5 | Macro5 group_summary를 Macro4 helper text 구조로 표시 |
| B1-02 | Combo1/Combo2 Risk-off 요약 복원 | MISSING_IN_MACRO5 | Final9 model_type별 현재 raw state 집계 |
| B1-03 | 현재 상태 요약을 카드 grid에서 Macro4 compact summary로 변경 | DIFFERENT_STRUCTURE | 카드 8개 제거 후보, 한 줄/두 줄 요약으로 치환 |
| B1-04 | 실행 안내 문구 추가 | MISSING_IN_MACRO5 | start/end event와 T+1 next date 표시 |
| B1-05 | 상태 시작일 표시 추가 | MISSING_IN_MACRO5 | `current_state_start_date` 연결 |
| B1-06 | 백테스트 비교표를 Combo2/Combo1 expander로 분리 | DIFFERENT_STRUCTURE | `model_type` 기준 분리 |
| B1-07 | 백테스트 표를 Macro4 HTML 스타일로 맞춤 | DIFFERENT_STYLE | `st.dataframe` 대신 HTML table 검토 |
| B1-08 | 지표별 상태표를 선택 후보 구성요소 기준으로 변경 | DIFFERENT_STRUCTURE | Final9 전체 snapshot table 대신 selected component table |
| B1-09 | 내부 ID/source parity 과노출 축소 | EXTRA_IN_MACRO5 | 고급 expander 내부로 이동 |
| B1-10 | label 한글화 및 Macro4 문구 parity | DIFFERENT_CONTENT | component label dictionary 정리 |

B1 count: 10

### B2 - 차트 표시

| ID | 항목 | 상태 | 권장 |
|---|---|---|---|
| B2-01 | 대표 차트 marker label/legend를 Macro4 톤으로 정렬 | DIFFERENT_CONTENT | Raw Risk 문구를 Macro4식 Risk 시작/종료로 맞춤 |
| B2-02 | T+1 투자 가능 보조선의 일반 표시 여부 재검토 | EXTRA_IN_MACRO5 | 기본 숨김 또는 고급 표시 |
| B2-03 | component chart expander 기본 펼침을 Macro4 Combo2와 맞춤 | DIFFERENT_STRUCTURE | 선택 후보 구성요소는 `expanded=True` |
| B2-04 | component chart height를 Macro4 component 기준 260으로 맞춤 | DIFFERENT_STYLE | 차트 높이 정렬 |
| B2-05 | component 시작/종료 event marker 추가 | DIFFERENT_CONTENT | ON square만으로 부족 |
| B2-06 | Core15 지표 차트 raw/EMA/threshold series 연결 | UI_DATA_WIRING_REQUIRED | 기존 Core15 frame 노출 필요 |
| B2-07 | secondary y-axis/benchmark overlay 방식 검토 | UI_DATA_WIRING_REQUIRED | Macro4 indicator chart parity 목적 |

B2 count: 7

### B3 - 최종 시각 회귀

| ID | 항목 | 상태 | 권장 |
|---|---|---|---|
| B3-01 | Macro4/Macro5 같은 viewport 스크린샷 비교 | REVIEW_REQUIRED | 로컬 Playwright 또는 수동 캡처 |
| B3-02 | 좁은 화면 카드/표 줄바꿈 확인 | REVIEW_REQUIRED | 상단 상태 영역 우선 |
| B3-03 | 기간 변경 2/5/10/20년 차트 반영 확인 | REVIEW_REQUIRED | Macro4와 동일 cut 기준 |
| B3-04 | Combo1 후보와 Combo2 후보 각각 화면 확인 | REVIEW_REQUIRED | Final9 양쪽 유형 모두 |
| B3-05 | Macro4 회귀 영향 없음 확인 | REVIEW_REQUIRED | Macro4 source hash 및 화면 주요 구조 비교 |
| B3-06 | Live 실패 시 Frozen 성과/차트 유지 확인 | REVIEW_REQUIRED | 현재 상태 영역만 계산 불가 처리 |

B3 count: 6

## 13. 수정 예상 파일

| 파일 | 예상 역할 | 비고 |
|---|---|---|
| `technical_signal_dashboard.py` | Macro5 UI 구조, 표, 차트 렌더 조정 | 다음 단계 수정 대상 |
| `kospi_macro5_runtime/page_adapter.py` | 표시용 raw/EMA/threshold/source mapping 컬럼 전달 | 필요한 경우만, 계산식 변경 금지 |
| `tests/test_kospi_macro5_d1c3*_page*.py` | route/mock/UI data shape 회귀 | 다음 단계 테스트 |
| `reports/kospi_macro5_d1c3b*_*.md` | 수정 결과 기록 | 보고서 |

이번 단계에서는 위 파일들을 수정하지 않았다.

## 14. 불확실한 항목

| 항목 | 상태 | 이유 |
|---|---|---|
| Macro4 대표 차트 height/margin 완전 동일값 | REVIEW_REQUIRED | `_make_macro6_combo_chart_from_snapshot` 내부 layout 추가 확인 필요 |
| Core15 모든 지표군 raw/EMA/threshold page 노출 가능성 | REVIEW_REQUIRED | runtime frame에는 일부 존재하나 `page_adapter` 반환에서 제거됨 |
| Macro5 visual parity의 실제 배포 화면 차이 | REVIEW_REQUIRED | 이번 감사는 코드 기준, 브라우저 스크린샷 비교는 B3 |

REVIEW_REQUIRED count: 3

## 15. 다음 단계 권고

1. D1-C3B.2에서는 B1만 먼저 수정한다. 목표는 Macro4와 같은 상단 요약, expander 분리, 백테스트 표, 지표별 상태표 구조 복원이다.
2. D1-C3B.3에서 B2 차트 표시를 수정한다. 이때 raw/EMA/threshold가 필요한 경우 page adapter에는 표시용 컬럼 전달만 추가한다.
3. D1-C3B.4에서 B3 시각 회귀와 Macro4 regression을 수행한다.

## 16. Safety Result

| 항목 | 결과 |
|---|---|
| logic changed | false |
| formula changed | false |
| signal changed | false |
| threshold changed | false |
| candidate changed | false |
| T+1 changed | false |
| availability changed | false |
| freshness changed | false |
| runtime changed | false |
| page_adapter changed | false |
| technical_signal_dashboard changed | false |
| test changed | false |
| deleted file | 0 |
| commit | false |
| push | false |
| deploy | false |

Final status: `AWAITING_USER_REVIEW_KOSPI_MACRO5_D1C3B1_UI_AUDIT`
