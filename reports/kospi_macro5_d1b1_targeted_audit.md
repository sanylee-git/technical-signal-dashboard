# KOSPI Macro5 D1-B.1 Targeted Audit

## 1. 한 줄 결론

현재 `🇰🇷 매크로 지표 5`는 2026-07-28 종료 Frozen reference viewer이며, 실전 Live Shadow나 운영 모델이 아니다. 실시간 사용 전에는 D1-C1 Live Engine, D1-C2 Freshness Defense, D1-C3 Macro6 UI parity integration이 필요하다.

## 2. 현재 Macro5 운영 상태

- 현재 Macro5는 Frozen Viewer인가?: `PASS` / `FROZEN_REFERENCE_VIEWER` — technical_signal_dashboard.py:12864 reads only kospi_macro5_assets; d1b manifest frozen_reference_mode=True
- 최신 데이터 자동 수집 기능이 있는가?: `MISSING` / `False` — technical_signal_dashboard.py:14458 uses frozen assets; implementation manifest live_extension_connected=False
- 매일 또는 매시간 재계산되는가?: `MISSING` / `False` — No sync bucket/network loader in macro5_kospi path; frozen_reference_end fixed.
- Cloud 재실행 시 최신 신호가 생성되는가?: `MISSING` / `False` — Cloud restart reloads bundled parquet/csv only.
- 현재 화면 상태를 실전 매매 참고 신호로 사용할 수 있는가?: `INCORRECT` / `False` — Shadow frozen reference only; actual_trading_ready=false in audit.
- 현재 상태 분류: `PASS` / `FROZEN_REFERENCE_VIEWER` — frozen_reference_end=2026-07-28; official_operating_model=False

## 3. 실전 매매 사용 가능 여부

- 판정: `불가`. Frozen 기준일은 2026-07-28이고, `official_operating_model=false`, `live_extension_connected=false`, `shadow_validation_completed=false`이다.

## 4. Macro6와 Macro5 핵심 차이

- Gap matrix row count: `31`
- Macro5가 Macro6 기능을 frozen/pass 형태로 충족하는 비율: `9.7%`
- 주요 차이: Macro6는 Yahoo/FRED live fetch, availability, K/L 재계산, source status panel을 가진 실시간 shadow 경로이고, Macro5는 bundled parquet/csv를 읽는 frozen viewer다.

## 5. Final9 Lineage 결과

- Final9 count: `9` / Combo1 `4` / Combo2 `5`
- Combo1 저장 raw bank parity: `2`
- Combo1 Core15 재계산 reference: `2`
- Combo2 Stage07C.2 저장 daily signal: `5`
- D1-B signal parity mismatch totals: raw `0`, T+1 `0`, start `0`, end `0`

## 6. Component 완전성 결과

- Final9 display component unique count: `41`
- Core15 component unique count: `24`
- Combo2 하위 Combo1 raw state unique count: `17`
- Core15 families used by Final9: `global_credit_stress, kospi_bollinger, kospi_hv_n80, kospi_natr_n80, kospi_rsi, us_10y_2y_spread, us_10y_3m_spread, us_10y_real_yield_level, us_10y_slope, us_hy_oas_level, us_ig_oas_level, usdkrw_level, vix_level, vix_spread`
- Core15 full universe families not present in Final9 visible components: `kospi_hv, kospi_index_level, kospi_natr`
- Live runtime parser/compute coverage: `MISSING` for KOSPI Core15. Frozen component signals exist.

## 7. Source Policy 결과

- HY/IG는 proxy-only: HY=`DBAA-DGS10`, IG=`DAAA-DGS10`; exact OAS stitching 금지.
- Credit Stress는 HY proxy, NFCI, VIX rolling z-score composite로 기록되어 있다.
- Macro6 source를 이름만 보고 재사용하면 안 되며 KOSPI `source_config_snapshot.yaml` 기준 adapter가 필요하다.

## 8. Availability 결과

- KOSPI OHLCV lag 0, USD/KRW/VIX/VIX3M/US rates/corporate yields lag 1, NFCI lag 3이 frozen source config에 기록되어 있다.
- Macro5 runtime은 availability를 새로 적용하지 않는다. 이미 계산된 frozen component states를 읽는다. Live Engine에서는 source별 lag를 재적용해야 한다.

## 9. Frozen↔Live parity 준비도

- 현재 준비도: `PARTIAL`. D1-A/D1-B frozen parity는 통과했지만 live path가 없어 overlap parity는 설계만 가능하다.
- 권장 overlap: 2019-01-01~2026-07-28 plus warmup, 최소 2020/2022/2024~2026 포함. Level 1 source, Level 2 Core15, Level 3 Combo1, Level 4 Combo2, Level 5 T+1/metric 순서로 검증한다.

## 10. KRX calendar·최신성 준비도

- 현재 구현: `없음`. Yahoo `^KS11` 마지막 행을 expected latest로 쓰는 자기참조 구조는 금지해야 한다.
- 권장 함수: `_kospi_latest_completed_trading_date()`, `_kospi_completed_trading_days()`, `_kospi_next_execution_date()`

## 11. Cloud stale 대응 준비도

- 현재 구현: `없음`. 독립 expected latest, actual latest, bypass retry, last-known-good, no-regression, source tail debug가 필요하다.

## 12. Missing/T+1 위험

- Missing 위험: live path에서 component missing을 False/Risk-on으로 처리하면 치명적이다. `valid_signal` 누락 시 계산 차단해야 한다.
- T+1 계약: `RAW_RISK_STATE; t1_position[t] = 1 - raw_risk_state[t-1]`. Combo2 하위 Combo1은 raw risk_state를 사용해야 하며 T+1을 중복 적용하면 안 된다.

## 13. UI 차이

- UI gap row count: `15`
- 첨부 이미지 기준 Macro5는 Macro6 대비 상태 요약, 그룹 백테스트 비교, source 최신성, raw/threshold component chart, HTML panel 구조가 부족하다.

## 14. P0~P3 Findings

- P0: `7`
- P1: `5`
- P2: `4`
- P3: `4`

## 15. D1-C 권장 순서

### D1-C1 · Live Engine
- 범위: KOSPI source loader, availability, Core15 parser/compute, required Combo1 raw state, Final9 Combo1/Combo2, T+1, historical overlap parity.
- Hard Fail: source policy mismatch, availability mismatch, raw/T+1 parity mismatch, missing-as-risk-on, Combo2 T+1 double-shift.
### D1-C2 · Freshness & Cloud Defense
- 범위: KRX calendar, expected latest, source latest, stale detection, bypass retry, last-known-good, no-regression, source consistency table.
- Hard Fail: stale source treated as current, source tail regression, KOSPI-derived source latest mismatch.
### D1-C3 · Macro6 UI Parity Integration
- 범위: Macro6 구조 clone, live/frozen state separation, source freshness table, component raw/threshold charts, warning/debug panels.
- Hard Fail: Macro6 regression, shared session/cache, final9 status implying official model.

## 16. 수정하지 않았다는 증거

- technical_signal_dashboard.py hash before report write: `beaa60322e921ab5632eaee48a1c5d052da0a29e0ec6d165333315fde80fd030`
- 감사 중 code/asset write 없음. 새 파일은 `reports/kospi_macro5_d1b1_*`만 생성.
- git add/commit/push/deploy 없음.

## 17. 최종 Gate

- `PASS_KOSPI_MACRO5_D1B1_TARGETED_AUDIT_READY`
- PASS_D1B1_CURRENT_STATE_CLASSIFIED: `PASS`
- PASS_D1B1_MACRO6_FEATURE_INVENTORY: `PASS`
- PASS_D1B1_MACRO5_FEATURE_INVENTORY: `PASS`
- PASS_D1B1_MACRO6_MACRO5_GAP_MATRIX: `PASS`
- PASS_D1B1_FINAL9_LINEAGE_AUDIT: `PASS`
- PASS_D1B1_CORE15_COMPONENT_COVERAGE_AUDIT: `PASS`
- PASS_D1B1_SOURCE_POLICY_AUDIT: `PASS`
- PASS_D1B1_AVAILABILITY_AUDIT: `PASS`
- PASS_D1B1_FROZEN_LIVE_PARITY_DESIGN: `PASS`
- PASS_D1B1_KRX_CALENDAR_DESIGN: `PASS`
- PASS_D1B1_CLOUD_FRESHNESS_DESIGN: `PASS`
- PASS_D1B1_MISSING_T1_AUDIT: `PASS`
- PASS_D1B1_UI_GAP_AUDIT: `PASS`
- PASS_D1B1_D1C_PHASE_PLAN: `PASS`
- PASS_D1B1_NO_CODE_CHANGE: `PASS`
- PASS_D1B1_NO_ASSET_CHANGE: `PASS`
- PASS_D1B1_NO_DEPLOYMENT: `PASS`
- PASS_D1B1_NO_GIT: `PASS`
