# KOSDAQ Macro7 D1 Frozen Replay Parity

- Gate: `PASS_KOSDAQ_MACRO7_D1_FROZEN_REPLAY_PARITY_READY`
- Mode: independent dashboard runtime; Frozen local assets only; network calls 0.
- Combo2 input: `CHILD_COMBO1_RAW_RISK_STATE`.
- Final T+1 application count: 1.
- Missing/invalid policy: `INVALID_NOT_RISK_ON`.

## Parity

| Layer | Total mismatch |
|---|---:|
| core | 0 |
| child_combo1_raw | 0 |
| final_combo1_raw | 0 |
| final_combo2_raw | 0 |
| final_t1 | 0 |

- D0 contract drift: 0
- Frozen asset hash mismatch: 0
- Validity-mask mismatch: 0
- Invalid component converted to Risk-on: 0
- Invalid component-days in official evaluation: 0
- Maximum CAGR/MDD/Calmar absolute delta: 8.327e-17

Raw intermediates (EMA, rolling inputs, and threshold series) have no authoritative stored reference and remain `NOT_AVAILABLE_REFERENCE`; exact parity is enforced for date, validity, state, and events.
