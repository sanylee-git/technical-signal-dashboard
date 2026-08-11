# Macro5 FRED Source-Level Parallel Fetch Production Local/Live Validation

## 1. Final Gate

`PASS_MACRO5_FRED_PARALLEL_PRODUCTION_LOCAL_LIVE_VALIDATED`

The production patch applies only the pilot-validated FRED source-level workflow parallelization with `max_workers=4`. No commit, push, or deploy was performed.

## 2. Starting State

| item | value |
|---|---|
| repo | `/Users/ibaeksan/Documents/프로젝트/technical-signal-dashboard` |
| branch | `main` |
| HEAD/origin before work | `b90c6093a97660c19738d63fcdf93c0fe7e7cfd3` |
| pilot report | `reports/macro5_fred_parallel_stability_parity_pilot.md` |
| pilot gate | `PASS_MACRO5_FRED_PARALLEL_STABILITY_PARITY_PILOT` |
| report duplicate before work | not present |

Allowed pre-existing untracked reports remained uncommitted.

## 3. Production Patch

| item | result |
|---|---|
| modified production file | `kospi_macro5_runtime/page_adapter.py` |
| added test file | `tests/test_kospi_macro5_fred_parallel_source_loader.py` |
| FRED max workers | `4` |
| Session reuse added | no |
| async/multiprocessing added | no |
| timeout/retry/BYPASS/freshness changed | no |
| source/provider/date range/cache changed | no |
| UI/design/chart changed | no |
| formula/model/K/L/T+1 changed | no |

The original source loop was split into `_load_source_frames()` and `_load_one_source_frame()`. Non-FRED sources still run sequentially. FRED sources run source workflow tasks in a `ThreadPoolExecutor(max_workers=4)`, then results are reassembled in the original `SOURCE_CONTRACTS` order.

## 4. Source Workflow Contract

| check | result |
|---|---|
| source-internal primary -> freshness -> optional BYPASS -> selection preserved | PASS |
| FRED HTTP flat fan-out avoided | PASS |
| `fetch_with_optional_bypass` reused | PASS |
| `fetch_source` reused | PASS |
| `evaluate_source_freshness` reused | PASS |
| `normalize_provider_dates_for_freshness` reused | PASS |
| worker shared mutable result writes | none |
| deterministic output ordering | PASS |
| unexpected source exception propagated | PASS |

## 5. Pre/Post Live Baseline

| metric | pre-patch sequential | post-patch production | change |
|---|---:|---:|---:|
| Macro5 total wall | 73.865s | 18.535s | 55.330s faster |
| FRED source wall | 65.433s | 10.153s | 55.280s faster |
| FRED HTTP count | 17 | 17 | 0 |
| BYPASS source count | 8 | 8 | 0 |
| max concurrent FRED tasks | 1 | 4 | +3 |
| HTTP status counts | `{'200.0': 17}` | `{'200.0': 17}` | no regression |
| HTTP exception counts | `{}` | `{}` | no regression |

Pre-patch baseline: `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_parallel_production_baseline_20260811.json`

Post-patch live result: `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro5_fred_parallel_production_after_patch_20260811.json`

## 6. Semantic Parity

| hash | pre-patch | post-patch | parity |
|---|---|---|---|
| source rows | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | `dfb035b8cc8b372fd03f49bbe9c0312f7350e00d135bdde08824b18add029864` | PASS |
| transformed/aligned | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | `e3dc68a6f88611aa0af40f91816cf56be6e832935c77b0d148b0e6e595d1bba4` | PASS |
| Final9 | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` | `1973abc60125cd4510e16d73a99491d8d895b7977da0c6d899f6a52ea2fffe7b` | PASS |

Fixed source-level contract is covered by mocked targeted tests. Live pre/post semantic hashes also matched exactly for source rows, transformed input, and Final9.

## 7. Latest/Freshness Non-Regression

| item | result |
|---|---|
| Macro5 live run success | PASS |
| source success non-regression | PASS |
| FRED request count non-regression | PASS |
| STALE/BYPASS contract non-regression | PASS |
| provider pressure increase | none detected |
| latest/freshness semantic hash regression | none detected |
| Final9 calculation success | PASS |

## 8. Tests

| command | result |
|---|---|
| `python3 -m py_compile kospi_macro5_runtime/page_adapter.py technical_signal_dashboard.py tests/test_kospi_macro5_fred_parallel_source_loader.py` | PASS |
| `pytest -q tests/test_kospi_macro5_fred_parallel_source_loader.py` | 3 passed |
| `PYTHONPATH=. pytest -q tests/test_kospi_macro5_live_kospi_partial_daily.py tests/test_kospi_macro5_d1c3a_page_wiring.py tests/test_kospi_macro5_d1c3a2_latest_history.py` | 11 passed |
| `PYTHONPATH=. pytest -q tests/test_kospi_macro5_d1c3b2u_state_label_table_fix.py tests/test_kospi_macro5_d1c3b2t_backtest_table.py tests/test_macro5_phase2f_detail_chart_cache.py` | 28 passed |
| `PYTHONPATH=. pytest -q` | 99 passed, 14 warnings |

Running selected pytest files without `PYTHONPATH=.` produced existing import-path collection errors in this environment. The same tests passed with repo root on `PYTHONPATH`.

## 9. Local Streamlit Smoke

| check | result |
|---|---|
| command | `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8519 --browser.gatherUsageStats false` |
| health endpoint | `200 ok` |
| server stopped after smoke | PASS |
| deploy performed | no |

## 10. Diff Audit

| item | result |
|---|---|
| UI/design semantic change | 0 |
| data-source semantic change | 0 |
| freshness/STALE/BYPASS semantic change | 0 |
| formula/model semantic change | 0 |
| production changed files | 1 |
| test changed files | 1 |

```text
kospi_macro5_runtime/page_adapter.py | 184 +++++++++++++++++++++++------------
 1 file changed, 121 insertions(+), 63 deletions(-)
```

Changed files:

```text
kospi_macro5_runtime/page_adapter.py
```

Current status snapshot:

```text
M kospi_macro5_runtime/page_adapter.py
?? reports/macro5_fred_parallel_production_local_live_validation.md
?? reports/macro5_fred_parallel_stability_parity_pilot.md
?? reports/macro5_fred_session_stability_parity_pilot.md
?? reports/macro5_phase3c1_payload_split_failure_rca.md
?? reports/macro5_provider_fetch_retry_23s_bottleneck_analysis.md
?? reports/macro5_provider_timing_trace.md
?? tests/test_kospi_macro5_fred_parallel_source_loader.py
```

## 11. Final Recommendation

`commit/push -> Cloud smoke` can proceed in a separate user-approved step. This step intentionally stopped after local validation.
