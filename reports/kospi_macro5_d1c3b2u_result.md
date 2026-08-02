# KOSPI Macro5 D1-C3B.2U State Label Table Parity

## Gate

PASS_KOSPI_MACRO5_D1C3B2U_STATE_LABEL_TABLE_PARITY_READY_FOR_B2

## Scope

- `technical_signal_dashboard.py` only for page/UI display logic.
- No runtime, page adapter, Frozen asset, manifest, config, or dependency changes.
- No candidate, K/L, signal, availability, freshness, or metric contract changes.

## Changes

- Macro4 and Macro5 preset labels now use the common display format:
  - `[조합1] role (지표 N개/KN/LN)`
  - `[조합2] role (조합1 N개/KN/LN)`
- Macro5 disabled component multiselect is synchronized to the selected candidate before render, preventing stale `Choose options`.
- Macro5 current state start and duration are recalculated from candidate raw risk-state history from the official evaluation start.
- Macro5 Cycle counts use Frozen T+1 position, completed non-invested episodes only, and short Cycle threshold `<= 20` trading sessions.
- Macro5 KOSPI hold row is shown first in Combo1 and Combo2 backtest tables.
- Macro4 S&P500 and Macro5 KOSPI candidate rows show CAGR ratio vs hold.
- Macro4 and Macro5 component status ON circles use `#FF8C69`; shared `_macro_status_circle()` default remains unchanged.
- Macro4 top two-line summary spacing matches Macro5; Macro5 current state lines match Macro4 spacing.
- Macro4 and Macro5 representative chart titles use the same preset display labels. Chart series, axes, dimensions, and legends were not changed.

## Validation

- Macro5 Final9 label coverage: `9 / 9`
- Macro5 Combo1 / Combo2 coverage: `4 / 5`
- Macro5 candidate order unchanged: PASS
- Macro5 KOSPI hold first row: PASS
- Macro5 CAGR ratio: PASS
- Macro5 latest state span sample: `2026-05-26`, duration `44`, raw state `1`
- Choose-options source check: PASS
- Child Combo1 hash-only label fallback removed: PASS
- Component ON color: `#FF8C69`
- Shared status helper default changed: false

## Tests

- `python3 -m py_compile technical_signal_dashboard.py`: PASS
- `python3 -m compileall -q technical_signal_dashboard.py kospi_macro5_runtime tests`: PASS
- Targeted pytest: `26 passed`
- Full pytest: `48 passed, 2 warnings`
- Streamlit local startup: `HTTP 200 OK` on `127.0.0.1:8537`

## Notes

- Some Combo2 child Combo1 assets do not include human role metadata. Those are displayed with deterministic fallback labels such as `[조합1] 구성 후보 (지표 N개/K/L)` instead of hash-only suffixes.
- B2 chart-detail work can proceed after visual confirmation.
