# KOSPI Macro5 D1-C3B.2 B1 Structure/Table Parity Result

Gate: `PASS_KOSPI_MACRO5_D1C3B2_B1_STRUCTURE_TABLE_PARITY_READY_FOR_B2`

## Scope

Visible 매크로 지표 5(internal `macro5_kospi`)의 B1 영역만 Macro4(internal `macro6`) 흐름에 맞춰 정리했다.

수정 범위:

- 상단 Combo2/Combo1 계산 가능 및 Risk-off 요약
- 프리셋 표시 순서와 사용자 표시명
- 리스크 기준 문구
- 현재 상태 compact summary
- Combo2/Combo1 백테스트 비교표 분리
- 선택 후보 구성요소 중심 지표별 상태표
- 일반 비교표의 내부 ID/manifest/hash 노출 축소

명시적 미수정:

- 차트 builder
- 차트 크기/축/legend/marker/expander 기본값
- Core15/Child Combo1/Final9 계산
- source adapter, availability, freshness, KRX calendar
- Frozen/Live 결합 계약

## Files

수정 파일:

- `technical_signal_dashboard.py`

신규 파일:

- `tests/test_kospi_macro5_d1c3b2_structure_table_ui.py`
- `reports/kospi_macro5_d1c3b2_result.md`

기존 untracked 감사 보고서:

- `reports/kospi_macro5_d1c3b1_ui_parity_audit.md`

삭제 파일 수: `0`

## UI Result

| 항목 | 결과 |
|---|---|
| 상단 그룹 요약 | ready |
| Combo2 계산 가능/Risk-off 요약 | ready |
| Combo1 계산 가능/Risk-off 요약 | ready |
| 현재 상태 compact panel | ready |
| Raw 상태와 T+1 상태 분리 | ready |
| 리스크 기준 문구 | `시작 K개 이상 ON / 종료 L개 이하 ON` |
| Combo2 비교표 | ready, 5 rows |
| Combo1 비교표 | ready, 4 rows |
| 선택 행 강조 | ready |
| 선택 후보 지표표 | ready |
| 기본 선택 후보 component 행 수 | 11 |
| 최신 사용값 표시 | ready, existing `source_rows` 기반 |
| 고급정보 이동 | ready |
| 일반 비교/상태표 내부 ID 노출 | 0 |

참고: 차트 expander 내부의 기존 component caption은 B2 차트 단계 범위로 유지했다.

## Invariance Result

| 항목 | 결과 |
|---|---|
| logic mismatch | 0 |
| formula mismatch | 0 |
| signal mismatch | 0 |
| candidate mismatch | 0 |
| threshold mismatch | 0 |
| T+1 mismatch | 0 |
| active-count mismatch | 0 |
| event mismatch | 0 |
| Frozen metric mismatch | 0 |
| availability mismatch | 0 |
| freshness mismatch | 0 |
| chart builder changed | false |
| chart size changed | false |
| chart axis changed | false |
| chart expander changed | false |
| Macro4 changed | false |
| Macro6 changed | false |
| Probe changed | false |

## Verification

Commands:

- `python3 -m py_compile technical_signal_dashboard.py`
- `python3 -m pytest tests/test_kospi_macro5_d1c3b2_structure_table_ui.py -q`
- `python3 -m pytest -q`
- `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8517 --browser.gatherUsageStats false`
- `curl -I 'http://localhost:8517/?page=market_macro'`

Results:

- `py_compile`: PASS
- D1-C3B.2 focused pytest: `5 passed`
- Full pytest: `27 passed, 2 warnings`
- Streamlit startup: PASS
- Local HTTP smoke: `HTTP/1.1 200 OK`

Warnings:

- Existing pandas FutureWarning in `kospi_macro5_runtime/page_adapter.py:302`; not introduced by this UI step.

## Next

B2 차트 단계 진행 가능. B2에서는 현재 보류한 chart height/margin/axis/legend/event marker/raw/EMA/threshold series/expander 기본 펼침 상태를 별도 수정 대상으로 다루는 것이 안전하다.

Final status: `AWAITING_USER_REVIEW_KOSPI_MACRO5_D1C3B2_B1_UI`
