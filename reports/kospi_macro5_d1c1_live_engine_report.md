# KOSPI Macro5 D1-C1 Live Engine & Frozen Parity

Final Gate: `PASS_KOSPI_MACRO5_D1C1_FROZEN_ENGINE_READY_LIVE_REVIEW`

## C1-A Frozen Replay

- Gate: `PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY`
- Core/component mismatch count: 0
- Final raw/T+1 mismatch count: 0
- Reference final rows: 51733
- Replay final rows: 65628
- Reference component rows: 478803
- Replay component rows: 576068

## C1-B Live Adapter Probe

- Gate: `REVIEW_KOSPI_MACRO5_D1C1B_LIVE_SOURCE_BINDINGS_INCOMPLETE`
- Live tail appended: False
- Missing live bindings: 10
- Live freshness policy: deferred to D1-C2

## Contract Notes

- Combo2 input is child Combo1 raw risk_state.
- Child Combo1 T+1 is not used inside Combo2.
- Final9 T+1 is applied once only.
- Missing signal values are not treated as Risk-on.
- Dashboard UI integration is not part of D1-C1.
