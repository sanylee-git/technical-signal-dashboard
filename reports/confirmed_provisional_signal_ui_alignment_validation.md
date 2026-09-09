# Confirmed/Provisional Signal UI Alignment Validation

## Scope

This validation covers the follow-up UI addendum only. Indicator formulas,
candidate definitions, K/L, hysteresis, T+1, Frozen metrics, source policy,
and unrelated tabs were not changed.

## Implemented

- The existing confirmed-to-provisional trading-session gap is now rendered on
  the `잠정신호` line for S&P1, KOSPI, KOSDAQ, NASDAQ, and S&P2.
- KOSDAQ, NASDAQ, and S&P2 component tables now label a provisional component
  date with its candidate/component confirmed basis when that is the only
  provenance available. No source-specific freshness claim is fabricated.
- KOSDAQ component-table headers are centered to match the cloned tables.
- Existing S&P1/KOSPI source-aware component labels remain on their existing
  path.

## Gates

| Gate | Result |
|---|---|
| Five-tab two-line confirmed/provisional layout | PASS |
| Gap rendered inline on provisional line | PASS |
| Gap counted from trading-session history | PASS |
| Component provisional/confirmed basis provenance | PASS |
| Candidate/K/L/T+1/model state unchanged | PASS by scoped diff and regression tests |
| New provider/network request | 0 |
| `PASS_CONFIRMED_PROVISIONAL_SIGNAL_UI_ALIGNMENT_ALL_FIVE_TABS` | PASS |

## Validation commands

- `python3 -m py_compile` on the eight changed Python modules: PASS
- `pytest -q tests/test_confirmed_provisional_ui_alignment.py`: 4 passed
- KOSDAQ UI/runtime focused suites: PASS
- NASDAQ UI/runtime focused suites: PASS
- S&P2 UI/runtime focused suites: PASS
- Macro6 summary/status focused suite: PASS
- KOSPI compact status suite excluding the pre-existing default-preset
  fixture: 6 passed, 1 deselected
- `git diff --check`: PASS

The full KOSPI compact-status file still contains one pre-existing fixture
failure in `test_b2v_default_preset_is_unique_combo2_main_and_invalid_state_recovers_to_it`.
It expects synthetic rows to carry the production `Main` label and is
unrelated to this addendum; it was not modified as part of the minimal UI
patch.

## Final gate

`PASS_CONFIRMED_PROVISIONAL_SIGNAL_UI_ALIGNMENT_ALL_FIVE_TABS`
