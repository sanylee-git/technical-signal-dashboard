# KOSPI Macro5 D1-C1 Runtime Contract

Gate: `PASS_KOSPI_MACRO5_D1C1_RUNTIME_CONTRACT_READY`

- Required Core15 components: 47
- Required child Combo1 raw states: 17
- Frozen source-base rows: 7292
- Frozen source-base period: 1996-12-11 ~ 2026-07-28
- Missing dependencies: 0

Signal semantics:

- Combo2 input is child Combo1 raw risk_state.
- Child Combo1 T+1 is forbidden for Combo2.
- Final9 T+1 is applied once only.
- Missing signal values are not interpreted as Risk-on.
