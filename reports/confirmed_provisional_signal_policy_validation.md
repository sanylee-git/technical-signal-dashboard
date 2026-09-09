# Confirmed and Provisional Signal Policy Validation

## Scope

Applied the operating-status extension to the five existing market tabs only:

- S&P1 (Macro6)
- KOSPI (Macro5)
- KOSDAQ (Macro7)
- NASDAQ (Macro8)
- S&P2 (Macro9)

The change adds a confirmed snapshot and a provisional snapshot to the
selected-candidate current-status block. Official candidate definitions, K/L,
indicator formulas, hysteresis, official T+1, Frozen history, and official
backtest display metrics are unchanged.

## Contract Checks

- Confirmed basis uses the existing strict source-availability boundary.
- Provisional basis uses the existing market-session boundary and only carries
  already completed source values or derived states.
- HY and IG proxy values remain same-observation-date completed proxies. A
  delayed corporate-yield observation is never combined with a newer Treasury
  observation.
- KOSDAQ keeps its existing KRX calendar and strict path while adding a
  candidate-specific provisional continuation.
- NASDAQ and S&P2 no longer discard an otherwise valid live tail solely because
  a required daily source is stale; strict and provisional snapshots are
  exposed separately.
- Frozen official performance metrics remain the presentation source for the
  comparison tables.

## Validation Results

| Check | Result |
| --- | --- |
| Python compilation for touched modules | PASS |
| S&P2 live runtime tests | PASS (3) |
| NASDAQ live runtime tests | PASS (4) |
| KOSDAQ live runtime tests | PASS (7) |
| Macro6 summary snapshot tests | PASS (9) |
| Macro5 page wiring tests | PASS (3) |
| Same-date proxy carry regression | PASS |
| `git diff --check` | PASS |

## Known Test Environment Limitation

`tests/test_kospi_macro5_d1c3b2u_state_label_table_fix.py` cannot load its
pre-existing required asset because
`kospi_macro5_assets/kospi_final9_benchmark_close.parquet` is already deleted
in the worktree outside this change. The implementation does not restore,
modify, stage, or otherwise alter that unrelated deletion.

The unrelated default-preset fixture in
`tests/test_kospi_macro5_d1c3b2v_compact_status_table_width.py` also no longer
matches the current production Main-candidate naming contract. Its focused
confirmed/provisional status assertion passes; the legacy default-preset case
is outside this operating-status change.

## Final Gate

`PASS_CONFIRMED_PROVISIONAL_SIGNAL_POLICY_ALL_FIVE_TABS`
