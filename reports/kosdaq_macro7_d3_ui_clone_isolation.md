# KOSDAQ Macro7 Stage 4 - UI Clone and Isolation

## Gate

`PASS_KOSDAQ_MACRO7_D3_UI_CLONE_ISOLATION_READY`

## Scope

- Added the `코스닥지표` route and the independent `kosdaq_macro7_ui.py` renderer.
- Renamed only the Macro5 navigation/page label to `코스피지표`; its internal route,
  runtime, assets, candidate contract, cache keys, and renderer are unchanged.
- Macro7 consumes the D2.1 presentation payload. It does not calculate Core signals,
  Combo1/Combo2 state, T+1, availability, freshness, or performance in the UI.

## Presentation Contracts

- Default display only: `combo2_m7_k4_l3_58c1eaea19e6d371` (Combo2 slot 1,
  `성과 대표`). This is not a new main assignment or ranking.
- Combo1 detail charts read `component_chart_history` only. They use supplied
  chart-ready fields such as EMA and thresholds without recomputation.
- Combo2 detail charts read child Combo1 raw risk-state from `component_history`
  plus `benchmark_history`. They do not synthesize indicator raw/EMA/threshold data.
- If a required presentation field is absent, the renderer displays an unavailable
  chart instead of inventing data. The Stage 4 blocked code is
  `BLOCKED_KOSDAQ_MACRO7_D3_PRESENTATION_FIELD_GAP`.

## Isolation and Cache

- Macro7-only runtime: `kosdaq_macro7_runtime`.
- Macro7-only assets: `kosdaq_macro7_assets`.
- Macro7-only state/widget/cache prefix: `macro7_kosdaq_`.
- Presentation payload cache key: live-data sync bucket only. Candidate, component,
  period, expander, and chart visibility do not trigger `run_live_runtime()`.
- Contract values: payload acquisition per render = 1; cache hit = 0; cache miss <= 1;
  `presentation_only_ui_change_causing_runtime_refetch = 0`.

## Validation

- D2.1 immutable baseline SHA validation: PASS (6/6 files unchanged).
- Targeted Stage 2/2.1/3 + Macro5 route tests: `18 passed`.
- Full suite: `126 passed, 21 warnings`.
- `python3 -m py_compile technical_signal_dashboard.py kosdaq_macro7_ui.py`: PASS.
- `git diff --check`: PASS.

The 21 full-suite warnings were pre-existing pandas/yfinance warnings from existing
Macro5/Macro6 tests; no test failures occurred.

## Explicit Non-Changes

- Research repository: unchanged.
- Stage 1 through D2.1 Macro7 runtime/assets: unchanged.
- Macro4, Macro5 calculation contracts, signals, charts, model selection, data
  loaders, cache keys, and UI body: unchanged.
- No commit, push, deploy, Cloud validation, or Stage 5 work was performed.
