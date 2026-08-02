# KOSPI Macro5 D1-C3B.3R Chart Regression Repair

## Gate

PASS_KOSPI_MACRO5_D1C3B3R_CHART_REGRESSION_FIXED_READY_FOR_VISUAL_REVIEW

## Scope

- Baseline commit: ef4d100
- Page: Macro5 KOSPI shadow dashboard
- Changed scope: chart schema normalization and chart trace rendering only
- Unchanged: Core15 formulas, candidate composition, K/L, hysteresis, T+1, metrics, assets, calendar, freshness, and Macro4/Macro6 chart functions

## Reproduced Issues

Using the actual Macro5 page adapter route:

```text
page_adapter
-> Frozen + Live combined history
-> candidate_signal_history
-> component_signal_history
-> benchmark_close_history
-> transformed_source_history
-> chart builders
```

the following regressions were confirmed:

- Final9 main chart could return `None` after Frozen + Live append because Frozen candidate reference rows lacked `valid_signal`, leaving historical rows as NaN after schema alignment.
- Combo2 component charts rendered binary raw-state/active-count step charts instead of Macro4-style market charts.
- Combo1 component charts could show only raw source series while omitting EMA/start/end or RSI/BB threshold traces.
- Combo2 child titles could expose raw combo IDs when the chart builder received an ID directly.

## Fix Summary

- Normalized Frozen candidate and component reference rows to `valid_signal=True` only when the official reference state columns are already present. Raw state or T+1 values are not filled.
- Preserved Live invalid rows. No blanket missing-value fill was added.
- Restored Combo1 component chart default traces:
  - level/proxy style: EMA, start line, end line
  - RSI: RSI, dynamic upper/lower thresholds
  - Bollinger: price, BB middle, BB upper, BB lower
  - raw source is shown only when the optional raw toggle is enabled
- Replaced Combo2 binary component plots with KOSPI line, risk background, start/end markers, and a compact K/L annotation.
- Added HV display labels so component labels do not fall back to opaque IDs.
- Added builder-level Combo2 title normalization to avoid child Combo1 raw ID exposure.
- Replaced the user-facing chart failure text with a generic warning: `최신 대표 차트를 표시할 수 없습니다.`

## Actual Route Verification

```text
calculation_status: CALCULABLE
Final9 main chart failures: 0
x_end mismatches: 0
component chart failures: 0
Combo2 binary trace issues: 0
Combo2 raw child title count: 0
basis_date: 2026-07-31
```

## Tests

```text
python3 -m py_compile technical_signal_dashboard.py kospi_macro5_runtime/page_adapter.py
python3 -m pytest tests/test_kospi_macro5_d1c3b3r_chart_regression.py -q
python3 -m pytest tests/test_kospi_macro5_d1c3*.py -q
```

Latest full D1-C3 run:

```text
53 passed
```

Warnings are existing Streamlit cache/Yahoo/FutureWarning notices and are not chart regression failures.
