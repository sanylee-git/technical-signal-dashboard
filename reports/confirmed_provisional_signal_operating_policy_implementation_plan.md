# Confirmed and Provisional Signal Operating Policy Plan

## Purpose

Add one consistent operational-signal contract to these five existing dashboard tabs:

- S&P1 (Macro6)
- KOSPI (Macro5)
- KOSDAQ (Macro7)
- NASDAQ (Macro8)
- S&P2 (Macro9)

The dashboard must show two snapshots for the selected candidate:

1. **Confirmed signal**: the latest date on which all inputs required by that
   candidate are available under its existing source/availability contract.
2. **Provisional signal**: the latest completed market session, using current
   inputs where available and the last valid completed value/state for delayed
   inputs.

This is an operating-presentation extension. It must not alter candidate
selection, K/L, component definitions, indicator formulas, hysteresis,
official T+1, Frozen history, or official backtest metrics.

## Scope and Non-Goals

Allowed changes:

- Each market runtime/presentation payload required to expose confirmed and
  provisional snapshots.
- Selected-candidate status UI and minimal freshness metadata.
- Focused tests and a new validation report.

Not allowed:

- Candidate reselection, K/L changes, threshold tuning, model formula changes,
  new data sources, direct OAS substitution, or historical metric recomputation.
- Writing into Frozen assets or changing prior reports.
- Changing unrelated dashboard tabs, pages, charts, tables, or styles.
- Network calls in tests.

## Common Semantic Contract

### Confirmed signal

For each candidate, `confirmed_basis_date` is the latest completed market
session for which every required component has a valid input under the
candidate's existing availability policy.

- HY Proxy remains `DBAA - DGS10` using a same-observation-date inner join.
- IG Proxy remains `DAAA - DGS10` using a same-observation-date inner join.
- Credit Stress remains the pinned combination of HY Proxy, NFCI, and VIX.
- A source observation and its model availability date remain distinct.
- No invalid/missing component may be interpreted as Risk-on.
- Hysteresis and official T+1 are replayed exactly once through the confirmed
  basis date.

### Provisional signal

`provisional_basis_date` is the latest completed market session permitted by
the tab's existing market-session policy.

For a delayed source:

- Preserve its last valid **completed source value or derived state**.
- Do not interpolate, fabricate, or use a future value.
- Do not recompute HY/IG from differently dated constituents. A delayed proxy
  must retain its last same-date-complete proxy value/state.
- Preserve the original candidate formula, K/L, validity semantics,
  hysteresis, and one official T+1 application.

The provisional snapshot is an operating status, not a replacement for the
Frozen official backtest contract.

### Date and lag display

The UI must display source dates unambiguously:

```text
Confirmed signal: basis date YYYY-MM-DD · ON/K · state
Provisional signal: basis date YYYY-MM-DD · ON/K · state
Delayed sources: source labels · confirmed basis gap N market sessions
```

Never display a bare `N days delayed` label. Calendar days and market sessions
must not be conflated. When useful, the UI may additionally show calendar days
in parentheses.

If the two snapshots are identical in basis date and state, render a compact
equivalence message while retaining both semantic labels. If the provisional
snapshot cannot be built, show the confirmed snapshot and an explicit
`PROVISIONAL_UNAVAILABLE` reason; never silently fall back to Frozen data.

## Per-Tab Runtime Work

### S&P1 and KOSPI

These pages already produce latest-market-date operating rows and expose source
freshness. Add a strict confirmed snapshot alongside the current operating
snapshot.

- Confirmed basis must be candidate-specific and use only required sources.
- Preserve the current operating row as the provisional snapshot.
- Audit that provisional HY/IG retains a complete same-date proxy value rather
  than combining stale corporate yields with a newer Treasury observation.

### KOSDAQ

Macro7 already has candidate-specific strict source bases. Use that existing
snapshot as the confirmed signal.

- Add a provisional continuation to the latest KRX completed session.
- Keep the existing strict snapshot unchanged.
- Preserve the KRX calendar and intraday/final-row contract.

### NASDAQ and S&P2

Macro8 and Macro9 currently discard their entire live tail when any required
source is stale and revert to their Frozen cutoff.

- Replace this all-or-nothing fallback with two outputs: strict confirmed and
  provisional latest-session snapshots.
- The strict path must append only through the common available basis, which
  should preserve the current no-fill contract.
- The provisional path may continue state/value carry only under the common
  provisional contract above.
- Runtime metadata must distinguish `CONFIRMED`, `PROVISIONAL`, and
  `PROVISIONAL_UNAVAILABLE`; `LIVE_TAIL` alone is not sufficient status.

## UI Placement

In each selected-candidate current-state block, render:

1. Confirmed signal line.
2. Provisional signal line.
3. Existing state-duration / segment-return / execution / transition line,
   sourced from the provisional snapshot when available, otherwise confirmed.

The existing design, colors, typography, divider spacing, charts, comparison
tables, and candidate controls remain unchanged. The two new lines use the
existing state color and ON/K formatting helpers.

## Validation Plan

### Contract tests

- Confirmed snapshot at a fully fresh fixture equals the provisional snapshot.
- Delayed DBAA/DAAA fixture keeps the last same-date-complete HY/IG proxy in
  provisional mode; it must not mix old corporate data with newer DGS10 data.
- Strict confirmed basis is capped at the latest common required availability.
- Provisional basis reaches the latest completed market session when its
  permitted carried state exists.
- Invalid/missing sources produce `PROVISIONAL_UNAVAILABLE`, never Risk-on.
- Hysteresis parity and `final_t1_application_count == 1` hold for both paths.
- Frozen prefix rows and official backtest display metrics remain byte/semantic
  unchanged.

### Tab-level checks

- One selected Combo1 and one selected Combo2 candidate per tab.
- Confirmed/provisional basis, active count, state, execution position, and
  delayed-source metadata are present.
- Candidate/period/component UI interactions reuse the existing payload and do
  not trigger an additional runtime fetch.
- KOSPI/KOSDAQ/NASDAQ/S&P1/S&P2 namespaces remain isolated.
- Existing targeted live-runtime and UI tests pass; add focused tests only for
  this new contract.
- `python3 -m py_compile` and `git diff --check` pass.

## Delivery Gates

Success:

`PASS_CONFIRMED_PROVISIONAL_SIGNAL_POLICY_ALL_FIVE_TABS`

Stop and report before changing semantics if any of the following is true:

- The exact required-source set for a candidate cannot be determined from its
  pinned runtime/manifest.
- A provisional proxy requires mixing different observation dates.
- A confirmed or provisional path would apply T+1 more than once.
- A change would alter Frozen rows or official performance metrics.

## Rollout Order

1. Read-only preflight: record current candidates, source contracts, Frozen
   cutoffs, and current basis behavior for all five tabs.
2. Implement shared semantic assertions only where existing code can use them
   without coupling market runtimes.
3. Add confirmed/provisional snapshots to NASDAQ and S&P2, then KOSDAQ.
4. Add strict confirmed snapshots to KOSPI and S&P1.
5. Wire the two-line current-state display in all five tabs.
6. Run focused parity/freshness/UI tests and inspect the final diff.
7. Stop for user review before commit, push, or deployment.

## Execution Approval

On 2026-09-09, the user approved implementation and requested commit and push
after the scoped validation succeeds. This approval supersedes only the final
review stop in the rollout order; every semantic and safety constraint above
remains unchanged.
