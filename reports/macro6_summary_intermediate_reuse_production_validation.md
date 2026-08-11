# Macro6 Summary Intermediate Reuse Production Validation

Final Gate: PASS_MACRO6_SUMMARY_INTERMEDIATE_REUSE_PRODUCTION_LOCAL_VALIDATED

Generated: 2026-08-12 KST

## 1. Git Baseline

| Item | Value |
|---|---|
| branch | `main` |
| start HEAD | `b0d88a3a0bcac870d4a59327f5b541fe676fdf1b` |
| start origin/main | `b0d88a3a0bcac870d4a59327f5b541fe676fdf1b` |
| latest commit | `b0d88a3 Reuse Macro6 selected snapshot signal frame safely` |
| lineage | `49122f9`, `5062d21` present |

Pre-existing allowed untracked reports:

- `reports/macro6_cold_bottleneck_analysis.md`
- `reports/macro6_cold_timing_trace.md`
- `reports/macro6_selected_detail_reuse_parity_pilot.md`
- `reports/macro6_postpatch_cold_retiming.md`
- `reports/macro6_summary_intermediate_reuse_parity_pilot.md`

## 2. Pilot Basis

Prior diagnostic pilot:

`PASS_MACRO6_SUMMARY_INTERMEDIATE_PARTIAL_REUSE_PARITY_PILOT`

Pilot result:

| Metric | Baseline | Reuse | Saving |
|---|---:|---:|---:|
| all-candidate summary wall | 27.580s | 6.284s | 21.296s |
| total fixed-input compute | 30.859s | 9.408s | 21.451s |

Pilot-proven boundary:

`summary phase` exact duplicate `_macro6_get_indicator_signal_frame`.

Pilot did not prove reuse of candidate final state, K/L, hysteresis, market-stage,
status, charts, provider calls, or source/freshness decisions.

## 3. Production Change

Modified production file:

- `technical_signal_dashboard.py`

Modified test file:

- `tests/test_macro6_phase2e_summary_snapshot.py`

Production boundary:

```text
_compute_macro6_operating_summary_map_cached
  -> creates run-local signal_frame_cache = {}
  -> _compute_macro6_operating_summary
  -> _compute_macro6_preset_signal_frame
  -> _compute_macro6_combo2_signal_frame / _compute_macro6_combo_signal_frame
  -> exact duplicate live _macro6_get_indicator_signal_frame hit
     -> defensive deep copy
  -> key miss
     -> original _macro6_get_indicator_signal_frame(...)
```

Scope is run-local to one summary-map calculation. There is no module-global cache,
Streamlit cache, disk cache, cross-user cache, cross-rerun cache, TTL cache, or
provider cache change.

## 4. Reuse Identity

The production key is semantic, not candidate based.

Included in identity:

- function identity
- indicator
- full cfg payload
- benchmark index fingerprint
- years
- benchmark name
- S&P series fingerprint
- sync bucket
- normalized source mode
- `raw_series_cache_semantic = performance_cache_not_output_contract`

`raw_series_cache` is treated as a performance cache, not an output contract. This
matches the pilot: identical output was determined by the semantic inputs above,
while `raw_series_cache` only avoids repeated raw-source preparation within the
same calculation.

## 5. Defensive Copy Contract

Production stores canonical signal frames as deep copies and returns deep copies
on cache hits.

This preserves the pilot mutation-safety contract. Direct-reference reuse was not
introduced.

## 6. Mismatch Fallback

If no exact identity hit exists, production calls the original
`_macro6_get_indicator_signal_frame(...)` path.

No new fallback, source substitute, simplified formula, candidate shortcut, or
status/chart shortcut was added.

## 7. Candidate-Specific Recompute Preserved

Still recomputed through existing code:

- candidate final state
- child Combo1 composition
- Combo2 composition
- K
- L
- hysteresis
- active count
- final risk state
- event metadata
- market-stage
- selected snapshot
- status panel
- component charts
- backtest tables

## 8. Existing b0d88a3 Optimization Preserved

The selected full snapshot exact duplicate reuse from `b0d88a3` remained active.

Fixed-input validation after this patch:

| Check | Result |
|---|---|
| selected full snapshot hash parity | PASS |
| selected snapshot elapsed | 0.165s |
| actual `_macro6_get_indicator_signal_frame` calls | 94 |
| selected snapshot duplicate signal recompute regression | 0 observed |

## 9. Tests

Commands:

```text
python3 -m py_compile technical_signal_dashboard.py
PYTHONPATH=. pytest -q tests/test_macro6_phase2e_summary_snapshot.py
PYTHONPATH=. pytest -q tests/test_macro6_phase2c_source_reuse.py tests/test_macro6_phase2f_detail_chart_cache.py
PYTHONPATH=. pytest -q tests/test_macro6_phase2e_summary_snapshot.py tests/test_macro6_phase2c_source_reuse.py tests/test_macro6_phase2f_detail_chart_cache.py tests/test_kospi_macro5_d1c3b2_structure_table_ui.py tests/test_kospi_macro5_d1c3b2r_visual_parity.py tests/test_kospi_macro5_d1c3b2t_backtest_table.py tests/test_kospi_macro5_d1c3b2v_compact_status_table_width.py
PYTHONPATH=. pytest -q
```

Results:

| Test | Result |
|---|---|
| py_compile | PASS |
| Macro6 summary targeted | 9 passed |
| Macro6 source/detail targeted | 7 passed |
| Macro6 + Macro5 targeted regression bundle | 48 passed |
| full pytest | 106 passed, 21 warnings |

Warnings were existing pandas/yfinance/Streamlit bare-mode warnings, not failures.

## 10. Added Regression Coverage

Added tests:

- exact duplicate summary signal-frame reuse
- identity mismatch fallback on cfg/sync/SPX/date changes
- defensive copy isolation
- semantic identity distinction
- existing selected snapshot reuse preservation through previous tests
- component chart and status paths remain separate

## 11. Fixed-Input Exact Parity

Validation script:

`/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_summary_intermediate_reuse_production_validate_20260812.py`

Result:

| Check | Result |
|---|---|
| all-candidate summary map | PASS |
| selected summary | PASS |
| selected candidate | PASS |
| K/L | PASS |
| selected state | PASS |
| group consensus | PASS |
| current market-stage | PASS |
| one-week-ago market-stage | PASS |
| selected full snapshot | PASS |
| main chart underlying data | PASS |
| combo event frame | PASS |
| component chart underlying data | PASS |
| status HTML | PASS |
| status table HTML | PASS |
| Combo2 backtest table | PASS |
| Combo1 backtest table | PASS |
| final selected semantic payload | PASS |

Hash diff count: 0.

## 12. Invocation Count

Pilot reference:

| Metric | Count |
|---|---:|
| summary signal invocations | 305 |
| unique exact identities | 38 |
| duplicate invocations | 267 |
| reuse hits | 267 |

Production fixed-input validation after patch:

| Metric | Count |
|---|---:|
| actual signal computes, all phases | 94 |
| selected candidate | `m8_8112998890601066` |
| candidate count | 11 |
| blocked candidate count | 0 |

The observed production actual compute count matches the pilot reuse-run count.

## 13. Fixed-Input Performance

Fixed-input current production validation:

| Area | Time |
|---|---:|
| total fixed-input compute | 8.826s |
| summary wall | 5.965s |
| selected snapshot | 0.165s |
| main chart | 0.073s |
| component charts | 2.205s |
| status | 0.222s |
| backtest panels | 0.033s |

Pilot baseline vs current production:

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| summary median | 27.580s | 5.965s | 21.615s |
| total fixed-input compute median | 30.859s | 8.826s | 22.033s |

Copy cost is included because production uses defensive deep copies on reuse hits.

## 14. Live Latest / Freshness Smoke

Live cold-like retiming after patch:

| Field | Value |
|---|---:|
| selected key | `macro6_combo2_1` |
| selected candidate | `m8_8112998890601066` |
| basis date | 2026-08-10 |
| S&P latest | 2026-08-10 |
| blocked candidates | 0 |
| selected state | Risk-on / off-cycle |
| selected ON count | 1 |
| detail charts available | 8 / 8 |

No latest/freshness/source regression was observed.

## 15. Local Cold-Like Performance

Local cold-like timing is not treated as direct Streamlit Cloud cold-start timing.

Before patch, post-`b0d88a3` retiming:

| Metric | Before |
|---|---:|
| cold-like total | 47.556-56.436s |
| Proxy-only spinner | 34.357-40.050s |
| warm rerun | 0.424s |

After patch:

| Run | Total | Proxy-only spinner | Summary map | Warm |
|---|---:|---:|---:|---:|
| cold-like 1 | 29.652s | 13.314s | 13.314s | - |
| warm 1 | 0.361s | 0.008s | 0.008s | 0.361s |
| cold-like 2 | 24.352s | 12.190s | 12.190s | - |

Observed local cold-like improvement:

- total: about 23-27s faster
- Proxy-only spinner: about 22-27s faster
- warm rerun remains fast

## 16. Local Streamlit Smoke

Command:

```text
python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8562 --server.address 127.0.0.1
```

Health endpoint:

```text
ok
```

The local server was stopped after the smoke check.

## 17. Semantic Diff Audit

| Area | Result |
|---|---|
| summary exact signal-frame reuse | changed as intended |
| UI/design/layout/text | 0 |
| source/provider | 0 |
| latest/freshness/availability/fallback | 0 |
| indicator formula/threshold | 0 |
| K/L | 0 |
| hysteresis | 0 |
| market-stage | 0 |
| candidate/model definition | 0 |
| status/chart semantics | 0 |
| Macro5 | 0 |

## 18. Git Diff Summary

Changed files:

- `technical_signal_dashboard.py`
- `tests/test_macro6_phase2e_summary_snapshot.py`
- `reports/macro6_summary_intermediate_reuse_production_validation.md`

Code diff summary before report creation:

```text
technical_signal_dashboard.py                 |  95 +++++++++++++++++++++---
tests/test_macro6_phase2e_summary_snapshot.py | 102 ++++++++++++++++++++++++++
```

No unrelated files were modified.

## 19. Final Status

`PASS_MACRO6_SUMMARY_INTERMEDIATE_REUSE_PRODUCTION_LOCAL_VALIDATED`

Commit/push/deploy were not performed.

Next step may proceed to final diff safety audit, selective commit/push, and
Streamlit Cloud smoke if the user approves.
