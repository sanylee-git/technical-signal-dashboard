# KOSPI Macro5 D1-C3B.3R2 Chart Semantics · Size · Period Safety Repair

## Gate

PASS_KOSPI_MACRO5_D1C3B3R2_CHART_SEMANTICS_PERIOD_SAFE_READY_FOR_VISUAL_REVIEW

## Scope

- Worktree: `/tmp/technical-signal-dashboard-d1c3b3r2-20260803`
- Base commit: `origin/main` (`5c34630055b156ead639c47e21287ebe5df22546`)
- Reference screenshots: `/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kospi/_handoff/차트사진_260803.zip`
- Commit / push / deploy: not executed

## Changes

- Macro5 chart period options now use `2년 / 3년 / 5년 / 7년 / 10년 / 15년 / 전체`.
- Legacy `20년` session values are safely mapped to `전체`.
- `전체` starts from the common valid start of benchmark, selected candidate, and selected component histories.
- Main and component charts use the selected candidate basis date as the fixed x-axis end.
- Component charts now use the same height as the representative chart.
- Axis titles such as `ON`, `ON 수`, `KOSPI`, `지표`, `가격`, and `RSI` are removed while tick labels remain.
- Combo1 component charts default to indicator semantics:
  - EMA/threshold type: EMA + start/end lines + KOSPI + risk background + event markers.
  - RSI type: RSI + upper/lower thresholds + KOSPI + risk background + event markers.
  - Bollinger type: price + BB middle/upper/lower + KOSPI + risk background + event markers.
  - Raw/source trace is only added when the auxiliary toggle is enabled.
- Combo2 child charts now show only KOSPI + child risk background + start/end markers.
- Combo2 child charts no longer show ON-count, raw state, K/L traces, EMA/threshold lines, binary step traces, or K/L annotations.
- Macro4 chart functions were not edited.

## Final9 Smoke

- calculation_status: `CALCULABLE`
- basis_date min/max: `2026-08-03` / `2026-08-03`
- main chart failures: `0`
- component chart failures: `0`
- x-axis end mismatches: `0`
- axis title violations: `0`
- chart height mismatches: `0`
- Combo1 trace issues: `0`
- Combo2 trace issues: `0`
- Combo2 annotation count: `0`
- visible `20년` period count: `0`
- period option set: `(2, 3, 5, 7, 10, 15, "all")`
- `전체` common start range across Final9: `1996-12-11` to `2008-04-01`

## Verification

- `python3 -m py_compile technical_signal_dashboard.py kospi_macro5_runtime/page_adapter.py`: PASS
- `python3 -m pytest tests/test_kospi_macro5_d1c3*.py -q`: PASS (`55 passed`)
- `git diff --check`: PASS
- `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8523`: startup PASS

## Modified Files

- `technical_signal_dashboard.py`
- `tests/test_kospi_macro5_d1c3b2_structure_table_ui.py`
- `tests/test_kospi_macro5_d1c3b2r_visual_parity.py`
- `tests/test_kospi_macro5_d1c3b2t_backtest_table.py`
- `tests/test_kospi_macro5_d1c3b3_chart_parity.py`
- `tests/test_kospi_macro5_d1c3b3r_chart_regression.py`
- `reports/kospi_macro5_d1c3b3r2_result.md`
