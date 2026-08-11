# Macro5 FRED Source-Level Parallel Fetch Stability / Parity Pilot

## 1. Pilot Gate

`PASS_MACRO5_FRED_PARALLEL_STABILITY_PARITY_PILOT`

Production code was not modified. This diagnostic pilot changed only source-task orchestration inside a repo-external harness.

## 2. Scope

| item | value |
|---|---|
| repo | `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard` |
| harness | `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_parallel_stability_pilot_20260811.py` |
| raw result | `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_parallel_stability_pilot_20260811.json` |
| max_workers | `4` |
| fixed as_of_utc | `2026-08-11T12:28:28.428725+00:00` |
| run isolation | child process per run |
| production code modified | no |

## 3. Independence / Orchestration Audit

| check | result |
|---|---|
| FRED source tasks share no business dependency before transformed-frame construction | PASS |
| Source-internal primary -> freshness -> BYPASS -> selection order preserved | PASS |
| FRED fetch/freshness/BYPASS/selection logic copied into harness | NO |
| Harness reassembled selected frames/source rows in SOURCE_CONTRACTS order | PASS |
| Yahoo/KOSPI/USDKRW path changed | NO |
| Session reuse combined with parallel pilot | NO |

## 4. Run Summaries

| run | variant | status | total_s | FRED wall_s | FRED source sum_s | FRED HTTP_s | FRED HTTP count | BYPASS sources | max concurrent FRED | HTTP statuses |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline_1 | baseline | success | 36.968 | 28.270 | 27.818 | 27.177 | 17 | 8 | 1 | `{'200.0': 17}` |
| parallel_1 | parallel | success | 9.747 | 1.323 | 4.039 | 3.159 | 17 | 8 | 4 | `{'200.0': 17}` |
| parallel_2 | parallel | success | 9.594 | 1.252 | 4.161 | 3.336 | 17 | 8 | 4 | `{'200.0': 17}` |
| baseline_2 | baseline | success | 12.998 | 3.271 | 2.822 | 2.285 | 17 | 8 | 1 | `{'200.0': 17}` |

## 5. Pair Validity

| pair | valid | reasons | baseline total_s | parallel total_s | baseline FRED wall_s | parallel FRED wall_s |
|---|---:|---|---:|---:|---:|---:|
| baseline_1 vs parallel_1 | True | `[]` | 36.968 | 9.747 | 28.270 | 1.323 |
| baseline_2 vs parallel_2 | True | `[]` | 12.998 | 9.594 | 3.271 | 1.252 |

## 6. Median Performance On Valid Pairs

| metric | baseline median | parallel median | improvement |
|---|---:|---:|---:|
| Macro5 total | 24.983s | 9.671s | 15.313s |
| FRED source wall | 15.770s | 1.287s | 14.483s |

## 7. Downstream Semantic Hashes

| run | source rows | transformed | Final9 |
|---|---|---|---|
| baseline_1 | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` |
| parallel_1 | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` |
| parallel_2 | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` |
| baseline_2 | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` |

## 8. Conclusion

FRED source-level parallel orchestration preserved operational parity and showed consistent wall-clock improvement in this diagnostic pilot. A separate minimal production patch can be considered, but was not applied here.
