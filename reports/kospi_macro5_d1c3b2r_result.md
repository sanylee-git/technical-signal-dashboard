# KOSPI Macro5 D1-C3B.2R Result

## Gate

`REVIEW_KOSPI_MACRO5_D1C3B2R_REQUIRED_TABLE_METRIC_NOT_AVAILABLE_WITH_RESIDUAL_B1_VISUAL_FIX_APPLIED`

The residual B1 visual corrections were applied without changing Macro4, Macro6, chart builders, runtime adapters, source loaders, calculation logic, candidate definitions, or signal semantics.

The full PASS gate is intentionally not claimed because the current frozen UI asset does not contain all table metrics required for Macro4-style B&H comparison rows and green relative multiples.

## Scope Applied

- Top summary now uses two Korean lines:
  - calculable / unavailable by `조합2` then `조합1`
  - Risk-off / basis date by `조합2` then `조합1`
- Page helper text no longer exposes `Live Shadow`, `Frozen reference`, `freshness`, `Runtime`, or parity terminology.
- Control column ratios were aligned to the Macro4 control row pattern used in the current file.
- KOSPI Macro5 multiselect chip CSS was tightened for smaller font, height, padding, line-height, border radius, and close icon size.
- Preset display labels use fixed slot metadata:
  - `slot=5`, `model_type=combo2` -> `[조합2] Main`
  - `slot=1`, `model_type=combo1` -> `[조합1] Main`
  - all other labels preserve existing fixed roles.
- Status panel wording was cleaned:
  - no duplicate K/L criteria line
  - no `T+1` text in the user-facing execution state
  - duration shown as trading-day count without duplicated wording
  - active components shown as a short current ON list.
- General vertical performance card was removed from the main body.
- Frozen evaluation contract and technical identifiers were moved to the bottom advanced expander.
- Backtest comparison table now shows only existing frozen metrics and current `active_count/component_count`.
- Component status table now uses `최신 사용값` and hides raw `FRESH`/`STALE`-style codes.

## Existing Asset Columns Used

- `slot`
- `model_type`
- `role`
- `candidate_id`
- `m_or_n`
- `K`
- `L`
- `cagr`
- `mdd`
- `calmar`
- `risk_off_ratio`
- `annual_turnover`
- `reference_signal_hash`
- `source_signal_parity`

Live current-state display uses existing page-adapter rows:

- `basis_date`
- `calculable`
- `raw_risk_state`
- `t1_position`
- `active_count`
- `component_count`
- `new_start_signal`
- `new_end_signal`
- `current_state_start_date`
- `current_state_trading_days`

## Required Table Metrics Not Available

The following requested Macro4-like table values are not present in the current frozen UI asset or page adapter output. They were not calculated or fabricated in this B1 visual correction stage:

- 10Y asset
- total asset
- 10Y MDD
- total cycle count
- short cycle count
- KOSPI buy-and-hold benchmark row
- B&H relative asset multiple
- B&H relative MDD multiple

Because of this, `B&H comparison row ready = false` and `green relative comparison ready = false`.

## Invariance

- Logic mismatch: `0`
- Formula mismatch: `0`
- Signal mismatch: `0`
- Candidate mismatch: `0`
- T+1 mismatch: `0`
- Active-count mismatch: `0`
- Frozen metric mismatch: `0`
- New source: `0`
- New candidate: `0`
- New dependency: `0`
- Deleted file: `0`

Protected function hashes remained unchanged for:

- `_macro5_kospi_build_main_chart`
- `_macro5_kospi_build_component_chart`
- `_make_macro6_combo_chart_from_snapshot`
- `_build_macro6_component_chart`
- `_build_macro6_indicator_chart`
- `render_macro6_proxy_final_section`
- `_build_macro6_status_panel`
- `_build_macro6_backtest_panel`
- `_macro6_state_duration_html`

## Verification

- `python3 -m py_compile technical_signal_dashboard.py`: PASS
- `python3 -m pytest tests/test_kospi_macro5_d1c3b2_structure_table_ui.py tests/test_kospi_macro5_d1c3b2r_visual_parity.py -q`: PASS
- `python3 -m pytest -q`: PASS, 34 passed, 2 existing pandas FutureWarnings
- `python3 -m compileall -q technical_signal_dashboard.py kospi_macro5_runtime tests`: PASS
- `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8529 --browser.gatherUsageStats false`: startup PASS
- `curl -I http://localhost:8529/`: HTTP 200

## B2 Readiness

Chart functions and chart call contracts were not changed. B2 can proceed for chart-specific parity work, but a full B1 PASS for the backtest table requires a later asset/metric contract that supplies B&H and cycle comparison values without recomputing them inside the page.
