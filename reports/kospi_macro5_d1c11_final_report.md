# KOSPI Macro5 D1-C1.1

Full Gate: `PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED_LIVE_REVIEW`

## C1-A.1 Frozen Runtime Hardening

- Gate: `PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED`
- Frozen raw/transformed source rows: 7292
- Display unique Core15 count: 24
- Full dependency parameterized Core15 count: 47
- Core15 parser missing: 0
- Core15 compute missing: 0
- Core15 state/event mismatch: 0
- Core15 validity mismatch: 0
- Child Combo1 count: 17
- Child raw-state mismatch: 0
- Child event mismatch: 0
- Final active-count mismatch: 0
- Final raw-state mismatch: 0
- Final T+1 mismatch: 0
- Metric tolerance fail: 0

## C1-B Live Binding

- Gate: `REVIEW_KOSPI_MACRO5_D1C1B_LIVE_SOURCE_BINDINGS_INCOMPLETE`
- Live binding implemented: 1/11
- Live freshness/stale policy: not implemented in D1-C1.1; deferred to D1-C2.

## Notes

- Combo2 input uses child Combo1 raw risk_state.
- Child Combo1 T+1 is not used inside Combo2.
- Final9 T+1 is applied once only.
- Macro5 UI remains in frozen reference viewer mode.
