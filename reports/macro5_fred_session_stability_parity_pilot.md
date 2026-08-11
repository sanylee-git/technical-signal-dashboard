# Macro5 FRED Session Reuse Stability / Parity Pilot

## 1. Pilot Gate

`NO_GAIN_MACRO5_FRED_SESSION_STABILITY_PARITY_PILOT`

Operational stability and semantic parity passed, but FRED `requests.Session()` reuse did **not** show a consistent or meaningful performance gain in the ABBA pilot. Production application is **not recommended** from this pilot alone.

## 2. Git 상태

| 항목 | 값 |
|---|---|
| repo | `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard` |
| branch | `main` |
| HEAD | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| recorded origin/main | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| production code modified | no |
| tests modified | no |
| assets/config modified | no |
| commit/push/deploy | no |

Expected existing untracked reports were present:

- `reports/macro5_phase3c1_payload_split_failure_rca.md`
- `reports/macro5_provider_fetch_retry_23s_bottleneck_analysis.md`
- `reports/macro5_provider_timing_trace.md`

## 3. Pilot 방식

Diagnostic harness:

```text
/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_session_stability_pilot_20260811.py
```

Raw result:

```text
/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_session_stability_pilot_20260811.json
```

The harness called the real Macro5 live loader:

```python
kospi_macro5_runtime.page_adapter.load_macro5_live_page_data()
```

No production code was edited. The session variant patched only the FRED fetch path inside the diagnostic process:

- Baseline: current production behavior; each FRED call creates its own `requests.Session()`.
- Session: one shared `requests.Session()` per Macro5 live-load run for FRED calls only.
- Session was closed after each run.
- Yahoo / yfinance path was not changed.
- timeout, URL, params, retry, STALE, BYPASS, selected attempt, freshness, availability, and downstream calculations were not changed.

## 4. 기존 병목 기준

Previous timing trace:

- Macro5 total: `44.823s`
- FRED HTTP GET total: `35.832s`
- FRED daily source STALE count: `8`
- BYPASS source count: `8`
- BYPASS selected count: `0`
- timeout / exception count: `0`

This pilot tested whether FRED connection reuse alone reduces that accumulated FRED request time.

## 5. Baseline / Session Request Contract

ABBA measurement order:

```text
Baseline 1
Session 1
Session 2
Baseline 2
```

All four runs completed successfully.

| run | variant | FRED HTTP count | BYPASS source count | request contract |
|---|---|---:|---:|---|
| baseline_1 | baseline | 17 | 8 | PASS |
| session_1 | session | 17 | 8 | PASS |
| session_2 | session | 17 | 8 | PASS |
| baseline_2 | baseline | 17 | 8 | PASS |

No request-count reduction occurred. Session reuse did not change STALE/BYPASS route count.

## 6. Source별 Live Fetch Success

All source runs were successful. The selected source semantic hashes were unchanged across baseline/session runs.

| item | result |
|---|---|
| source success regression | none |
| exception count | 0 |
| timeout exception count | 0 |
| selected source frame semantic parity | PASS |
| source rows semantic hash parity | PASS |

## 7. Latest Observation / Usable Date 비교

Pair-level source rows were identical for the comparison pairs:

- Pair 1: `baseline_1` vs `session_1`
- Pair 2: `baseline_2` vs `session_2`

Compared fields:

- `source_id`
- `fetch_status`
- `freshness_status`
- `expected_latest_observation_date`
- `actual_latest_observation_date`
- `selected_attempt`
- `row_count`

Result:

```text
latest / usable date regression = 0
```

## 8. Freshness 비퇴보 검증

All four runs produced identical source freshness semantics.

| 항목 | 결과 |
|---|---|
| freshness_status regression | 0 |
| source success regression | 0 |
| selected_attempt regression | 0 |
| row_count regression | 0 |

## 9. STALE / BYPASS / Fallback Parity

| 항목 | 결과 |
|---|---|
| STALE daily FRED sources | unchanged |
| BYPASS source count | `8` in every run |
| BYPASS selected count | `0` |
| selected_attempt | `1` for all sources |
| selected_reason for BYPASS sources | `BYPASS_OLDER_OR_NOT_BETTER_REJECTED` |
| fallback provider used | none |

Session reuse did not alter the STALE/BYPASS contract.

## 10. Live Data Overlap / Semantic Parity

The following hashes were identical across all four runs:

| hash | value |
|---|---|
| source_rows_semantic_hash | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` |
| transformed_semantic_hash | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` |
| final9_semantic_hash | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` |

## 11. 동일-입력 Downstream Parity

Pilot-level downstream parity passed:

```text
selected source semantic parity -> PASS
transformed/aligned semantic parity -> PASS
Final9 semantic parity -> PASS
```

Full UI/chart parity was intentionally left for a future production-patch stage. Since this pilot is transport-only and production code was not modified, chart/UI rendering was not re-tested here.

## 12. Macro5 전체 Timing

| run | variant | Macro5 total_s | source_total_s | FRED HTTP_s | Yahoo_s |
|---|---|---:|---:|---:|---:|
| baseline_1 | baseline | `37.068` | `28.913` | `26.425` | `1.886` |
| session_1 | session | `29.402` | `21.347` | `20.178` | `0.678` |
| session_2 | session | `39.651` | `31.697` | `30.483` | `0.691` |
| baseline_2 | baseline | `32.531` | `24.694` | `23.491` | `0.614` |

Median comparison:

| metric | baseline median | session median | session improvement |
|---|---:|---:|---:|
| Macro5 total | `34.799s` | `34.527s` | `+0.272s` |
| FRED HTTP | `24.958s` | `25.330s` | `-0.373s` |
| source total | `26.804s` | `26.522s` | `+0.281s` |
| Yahoo | `1.250s` | `0.684s` | not attributable to FRED Session |

Positive means Session was faster. Negative means Session was slower.

## 13. FRED Primary / BYPASS Timing

This pilot recorded FRED HTTP totals. It confirms:

- FRED HTTP count stayed at `17`.
- BYPASS source count stayed at `8`.
- No BYPASS was selected.
- Session reuse did not reduce FRED HTTP time consistently.

## 14. Pair별 성능 변화

### Pair 1: Baseline 1 vs Session 1

| metric | baseline_1 | session_1 | change |
|---|---:|---:|---:|
| Macro5 total | `37.068s` | `29.402s` | Session faster by `7.666s` |
| FRED HTTP | `26.425s` | `20.178s` | Session faster by `6.247s` |
| pair validity | PASS | PASS | valid |

### Pair 2: Baseline 2 vs Session 2

| metric | baseline_2 | session_2 | change |
|---|---:|---:|---:|
| Macro5 total | `32.531s` | `39.651s` | Session slower by `7.121s` |
| FRED HTTP | `23.491s` | `30.483s` | Session slower by `6.992s` |
| pair validity | PASS | PASS | valid |

The two valid pairs disagree. This is network variance / no stable gain, not a reliable performance improvement.

## 15. Network Variance

Network variance was substantial:

- Same request contract
- Same hashes
- Same source/freshness/BYPASS state
- Opposite performance direction across two valid pairs

This means FRED Session reuse alone is not proven to be a durable improvement.

## 16. Operational Stability 판단

Operational stability passed.

| 항목 | 결과 |
|---|---|
| current Macro5 live loader success | PASS |
| source success non-regression | PASS |
| latest date non-regression | PASS |
| freshness non-regression | PASS |
| STALE/BYPASS parity | PASS |
| selected source parity | PASS |
| transformed / Final9 parity | PASS |

## 17. Production 적용 안전성

Safety looked acceptable in the diagnostic harness, but performance value was not proven.

Do not apply to production yet because:

- FRED HTTP median did not improve.
- One valid pair improved and the other valid pair worsened.
- The observed problem is accumulated serial FRED latency and BYPASS call count, not clearly per-request connection setup overhead.

## 18. 코드 복잡도 대비 성능 가치

Session reuse adds code surface but did not show a stable gain.

Current recommendation:

```text
Do not implement FRED Session reuse as the next production patch.
```

The better next investigation is:

1. FRED parallel fetch parity pilot, or
2. STALE/BYPASS policy contract review.

However, STALE/BYPASS policy changes are not a simple performance optimization; they can alter freshness defense and must be treated as a contract decision.

## 19. 다음 단계 추천

Recommended next step:

```text
Macro5 FRED Parallel Fetch — Diagnostic Parity Pilot
```

Scope:

- production code zero-diff
- FRED-only diagnostic harness
- keep request contract per source
- preserve STALE/BYPASS semantics
- deterministic source order in output
- exact selected source / transformed / Final9 parity
- compare wall-clock speed

If parallel fetch is too risky, pause optimization and keep current production behavior.

## 20. Final Report Answers

1. **Pilot Gate**  
   `NO_GAIN_MACRO5_FRED_SESSION_STABILITY_PARITY_PILOT`

2. **valid pair 수**  
   `2 / 2`

3. **Baseline / Session Macro5 시간**  
   Baseline median `34.799s`, Session median `34.527s`.

4. **FRED 시간 개선량**  
   FRED median changed from `24.958s` to `25.330s`; Session was not better.

5. **최신 데이터 수집 비퇴보 여부**  
   PASS.

6. **source success / freshness 비퇴보 여부**  
   PASS.

7. **STALE/BYPASS parity**  
   PASS. BYPASS count `8` in every run; selected attempt unchanged.

8. **selected source / transformed / Final9 parity**  
   PASS.

9. **Session production 적용 추천 여부**  
   Not recommended.

10. **production code/test/asset diff**  
    `0`.

11. **commit/push/deploy**  
    Not performed.

