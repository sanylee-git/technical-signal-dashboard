# KOSDAQ Macro7 D2.1 Presentation Payload Validation

- Gate: `PASS_KOSDAQ_MACRO7_D2_1_PRESENTATION_PAYLOAD_READY`
- Scope: chart-ready presentation payload only; Stage 3 state and Live semantics are unchanged.
- Final10: `10`; exact D0 order: `True`
- Default display candidate: `combo2_m7_k4_l3_58c1eaea19e6d371`
- UI initial-display semantics: `UI_INITIAL_DISPLAY_ONLY`; Main assignment: `False`

## Payload Checks

- Chart state parity mismatch: `0`
- Candidate history after basis date: `0`
- Component history after parent basis date: `0`
- Benchmark history after candidate basis date: `0`
- Frozen display metric max absolute delta: `1.929e-10`
- UNAVAILABLE interpreted as Risk-on: `0`
- UI-side model calculation count: `0`
- Presentation runtime forbidden dependency hits: `0`
- D0-D2 immutable drift: `0`

## Payload Shapes

- candidate_history: `[45310, 11]`
- component_history: `[494454, 11]`
- component_chart_history: `[333000, 22]`
- benchmark_history: `[74000, 3]`
- performance_history: `[45310, 16]`
- frozen_display_metrics: `[20, 8]`

## Live Boundary

- last_market_row_date: `2026-08-14`
- last_market_row_status: `FINAL`
- last_valid_close_date: `2026-08-14`
- last_valid_close_value: `864.65`
- latest_completed_session: `2026-08-14`
- frozen_rows_overwritten: `0`
- live_rows_on_or_before_cutoff_used_for_runtime: `0`
- duplicate_date_count: `0`
- live_tail_first_date: `2026-07-29`
- live_tail_last_date: `2026-08-14`
- live_tail_row_count: `13`
