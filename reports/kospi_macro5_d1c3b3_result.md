# KOSPI Macro5 D1-C3B.3 Result

## Gate

PASS_KOSPI_MACRO5_D1C3B3_CHART_PARITY_READY

## Scope

- Updated Macro5 KOSPI representative and component chart builders only.
- Preserved Macro4 chart functions and existing KOSPI runtime calculation assets.
- No formula, candidate, K/L, source contract, or asset changes.

## Changes

- Main Macro5 chart now uses Macro4-style height, margin, title, legend, and grid contract.
- Chart x-range is explicitly anchored to the selected candidate basis date instead of each component frame's last date.
- Component charts now use KOSPI benchmark dates as the canonical x-axis and left-join component history to avoid truncating KOSPI.
- Component charts no longer use the red ON-square proxy.
- Combo1 component charts show the component indicator series on the left axis and KOSPI on the right axis; auxiliary EMA/threshold lines are available through the "보조선 표시" toggle.
- Combo2 component charts show child Combo1 active count and K/L lines on the left axis and KOSPI on the right axis.
- Risk-off background and start/end triangle markers are rendered on main and component charts.
- Component expanders are open by default.
- Technical state/reference captions were removed from the normal chart area and remain available through the advanced model/data expander.
- Page adapter now passes through transformed source history and component start/end/active_count fields already computed by the runtime.

## Validation

- `python3 -m py_compile technical_signal_dashboard.py kospi_macro5_runtime/page_adapter.py`: PASS
- `pytest tests/test_kospi_macro5_d1c3b3_chart_parity.py tests/test_kospi_macro5_d1c3b2v_compact_status_table_width.py tests/test_kospi_macro5_d1c3a2_latest_history.py -q`: PASS, 13 tests
- Frozen Final9 chart smoke:
  - candidates: 9
  - main chart failures: 0
  - component charts checked: 79
  - component chart failures: 0
  - x-axis end mismatches: 0
- Streamlit local startup on port 8517: PASS

## Notes

- Live extension remains dependent on the existing Macro5 live runtime. If a component history is missing sessions through the selected basis date, the chart builder returns unavailable rather than inventing or forward-filling state.
- Normal UI wording now uses "보조선 표시" for the Macro5 auxiliary trace toggle.
