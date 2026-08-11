# Macro6 Component Chart Intermediate Reuse Production Validation

## Final Gate

`PASS_MACRO6_COMPONENT_CHART_INTERMEDIATE_REUSE_PRODUCTION_LOCAL_VALIDATED`

Commit/push/deploy/cache clear: none.

## Git Baseline

- Branch: `main`
- Start HEAD / origin/main: `2363dff1c6eab24a4bf8fec3e0e1fc0f8646bccc`
- Baseline commit: `2363dff Reuse Macro6 summary indicator signal frames safely`
- Pilot report: `reports/macro6_selected_component_chart_preparation_audit.md`
- Pilot JSON: `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_component_chart_reuse_pilot_20260812.json`

## Production Reuse Boundary

Applied only to selected Macro6 Combo2 component chart preparation:

- A run-local `signal_frame_cache = {}` is created inside the selected component chart batch.
- The cache is passed through `_build_macro6_component_chart_cached(...)`.
- It reaches `_build_macro6_component_chart(...)`.
- Existing `_compute_macro6_combo_signal_frame(..., signal_frame_cache=...)` performs exact-identity hit/miss and defensive copy.

No new global/session/Streamlit/disk cache was added.

## Scope Kept Unchanged

Untouched:

- lazy rendering / expander state
- UI layout/design/text
- provider/source/query/timeout/retry/fallback contracts
- freshness/availability/basis-date logic
- K/L, hysteresis, market stage
- candidate/model computation
- status panel
- final payload
- Plotly figure construction semantics
- Macro5

Must-recompute areas remain per component:

- component combo assembly
- price alignment
- risk background
- start/end markers
- annotation
- Plotly figure object

## Fixed-Input Production Validation

Diagnostic:

`/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_component_chart_production_validate_20260812.json`

Selected candidate:

- Key: `macro6_combo2_1`
- Candidate: `m8_8112998890601066`
- Components: 8
- Basis date: `2026-08-11`
- SPX latest: `2026-08-11`

Results:

| Metric | No shared cache | Production batch reuse |
|---|---:|---:|
| Component chart wall time | 7.616s | 1.154s |
| Indicator signal computes | 56 | 23 |
| Unique exact identities | n/a | 23 |
| Reuse hits | n/a | 33 |
| Chart hash diffs | n/a | 0 |

Parity:

- Figure semantic parity: PASS
- Summary hash unchanged: PASS
- Selected snapshot event hash unchanged: PASS
- Selected basis date unchanged: PASS

Provider/source call counts decreased in the reuse run because exact duplicate signal-frame computations were removed. This is allowed. There was no provider/source/fallback/freshness contract change.

## Cold-Like / Warm Retiming

Diagnostic:

`/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_component_chart_reuse_cold_retiming_20260812.json`

New Python process only; no cache clear.

| Run | Total | Summary map | Component charts | Status panel | Warm |
|---|---:|---:|---:|---:|---:|
| cold_1 | 24.270s | 12.154s | 6.438s | 5.295s | n/a |
| cold_2 | 24.694s | 12.924s | 6.215s | 5.188s | n/a |
| warm_1 | 0.341s | 0.009s | 0.040s | 0.181s | yes |

Cold-like run details:

- Detail figures: 8
- Missing detail figures: 0
- Run-local signal identities: 23
- Signal-frame calls in cold-like path: 61
- Yahoo calls in cold-like path: 26
- FRED calls in cold-like path: 129

Interpretation:

- Fixed-input chart preparation shows the cleanest reuse effect.
- Cold-like end-to-end timing still includes provider/network/status costs, so the visible selected-detail path improves more modestly.
- The status panel remains a separate bottleneck and was intentionally not changed.

## Tests

Commands:

- `python3 -m py_compile technical_signal_dashboard.py`
- `PYTHONPATH=. pytest -q tests/test_macro6_phase2f_detail_chart_cache.py tests/test_macro6_phase2e_summary_snapshot.py tests/test_kospi_macro5_d1c3b2_structure_table_ui.py::test_macro5_b1_chart_and_macro4_functions_are_unchanged tests/test_kospi_macro5_d1c3b2r_visual_parity.py::test_b2r_chart_and_macro4_functions_are_unchanged`
- `PYTHONPATH=. pytest -q`

Results:

- `py_compile`: PASS
- Targeted tests: `18 passed`
- Full pytest: `108 passed, 21 warnings`

Added targeted coverage:

- exact duplicate component-chart signal-frame reuse
- identity mismatch cache miss
- existing detail chart cache behavior unchanged
- Macro6/KOSPI guard hash updates for intended Macro6 function changes only

## Local Streamlit Smoke

Command:

- `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8765 --server.address 127.0.0.1`

Result:

- HTTP status: `200`
- Server stopped normally

## Diff Audit

Production file changed:

- `technical_signal_dashboard.py`

Test files changed:

- `tests/test_macro6_phase2f_detail_chart_cache.py`
- `tests/test_kospi_macro5_d1c3b2_structure_table_ui.py`
- `tests/test_kospi_macro5_d1c3b2r_visual_parity.py`
- `tests/test_kospi_macro5_d1c3b2t_backtest_table.py`

Semantic diff:

- UI/design change: 0
- lazy/render behavior change: 0
- chart definition/value semantic change: 0
- source/latest/freshness logic change: 0
- K/L/hysteresis/market-stage change: 0
- status panel change: 0
- Macro5 change: 0

## Next Step

Proceedable:

`READY_FOR_FINAL_SAFETY_AUDIT_THEN_SELECTIVE_COMMIT_PUSH`

Recommended next bottleneck after commit/deploy verification:

- Macro6 selected status panel timing audit/reuse candidate, because status still takes about 5.2s in cold-like runs.
