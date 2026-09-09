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

## Revision Addendum: Availability and Provenance Corrections

This addendum is authoritative for the current five-tab correction. It does
not change candidate selection, K/L, indicator formulas, hysteresis, official
T+1, Frozen history, or official performance metrics.

The observed differences are treated as four independent classes:

1. S&P1 and KOSPI currently use the weekly NFCI availability date as the
   confirmed bottleneck. A valid weekly carry-forward value must not lower the
   confirmed basis date. Under the current source state, the expected result
   is confirmed 2026-09-04, while NFCI remains displayed as
   `2026-09-02 · weekly update` in source provenance.
2. S&P2 can silently return its Frozen cutoff when the live market tail cannot
   be built. A Frozen date must never be presented as a current operating
   signal after a live acquisition failure. The current snapshot must instead
   be marked `PROVISIONAL_UNAVAILABLE` with the failure reason.
3. NASDAQ, KOSDAQ, and S&P2 currently append a candidate confirmed date to
   component rows. Component tables must show source provenance, not a parent
   candidate basis date.
4. NASDAQ, KOSDAQ, and S&P2 use fixed table widths and non-wrapping cells,
   which causes source-provenance text to overflow. Their component tables
   must use the S&P1 table structure and wrapping behavior.

The following distinction is mandatory:

```text
source observation date
    the date of the source observation itself

effective available date
    the market session on which that observation can be used under its
    existing availability contract

confirmed basis date
    the common completed-session date through which all required sources are
    valid under their existing contracts

provisional basis date
    the latest completed market session available to the operating path
```

The source-provenance date and the confirmed basis date must not be substituted
for one another.

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
- A weekly source in an existing allowed carry-forward state, such as NFCI
  with `NO_NEW_RELEASE_EXPECTED` or another already-authorized cadence state,
  does not by itself lower `confirmed_basis_date` to its last release date.
  Its value is carried only within the existing freshness contract. A stale,
  errored, invalid, or unauthorized cadence state remains blocking and must
  not be carried.
- The confirmed basis is calculated from each required source's effective
  confirmed limit, not from the oldest raw observation date. No fixed date such
  as 2026-09-04 may be hard-coded.
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

For source-provenance text in the component status tables, circled-number
prefixes are display-only and must use plain Arabic numbering with a period:

```text
4. 신용스트레스 2026-09-02 · 주간 업데이트
```

This notation change must not alter indicator IDs, component ordering, source
mapping, freshness dates, or any signal calculation.

The source-provenance text must follow this shape when applicable:

```text
oldest used value 4. Credit Stress 2026-09-02 · weekly update
```

The displayed oldest source may be weekly and may therefore precede the
confirmed basis date. That is intentional. It must remain separate from the
confirmed/provisional lines above.

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
- Exclude an allowed weekly carry-forward source from the confirmed-date
  bottleneck calculation while retaining it in the source-provenance display.
- For KOSPI, do not use `source_bottleneck_actual_date` directly when that
  field identifies a cadence-carried weekly source. Derive the effective
  confirmed limit from the existing freshness contract instead.
- For S&P1, do not take the minimum of raw indicator `latest_date` values when
  the indicator is a composite containing a valid weekly input. Use effective
  source availability for the confirmed snapshot and keep the raw source date
  only in the table text.
- Combo2 status rows must resolve their child candidate component IDs and
  required source families before building provenance. A child candidate basis
  date is not a substitute for the child's source provenance.
- Preserve the current operating row as the provisional snapshot.
- Audit that provisional HY/IG retains a complete same-date proxy value rather
  than combining stale corporate yields with a newer Treasury observation.

### KOSDAQ

Macro7 already has candidate-specific strict source bases. Use that existing
snapshot as the confirmed signal.

- Add a provisional continuation to the latest KRX completed session.
- Keep the existing strict snapshot unchanged.
- Preserve the KRX calendar and intraday/final-row contract.
- Replace the generic `provisional · confirmed YYYY-MM-DD` component suffix
  with source-provenance text resolved from the selected child's underlying
  components and source status.

### NASDAQ and S&P2

Keep the existing Frozen-prefix plus Live-tail model contract and verify both
the local and deployed paths. The current local runtime is expected to produce
the latest live basis and a separate strict confirmed basis; a deployed S&P2
screen stuck at the Frozen cutoff is treated as a runtime acquisition or
deployment/cache failure, not as a valid current signal.

- The strict path must append only through the common effective available basis
  and preserve the current no-fill contract.
- The provisional path may continue state/value carry only under the existing
  provisional contract above.
- If the live market source is empty or the live tail cannot be constructed,
  return `PROVISIONAL_UNAVAILABLE` and an explicit reason. Do not reuse the
  Frozen cutoff as the current operating basis and do not silently render
  `FROZEN_CUTOFF` as a live date.
- Runtime metadata must distinguish `CONFIRMED`, `PROVISIONAL`, and
  `PROVISIONAL_UNAVAILABLE`; `LIVE_TAIL` alone is not sufficient status.
- Replace the generic component suffix with source-provenance text resolved
  from the selected component or child-combo source mapping.

## UI Placement

In each selected-candidate current-state block, render:

1. Confirmed signal line.
2. Provisional signal line.
3. Existing state-duration / segment-return / execution / transition line,
   sourced from the provisional snapshot when available, otherwise confirmed.

The existing design, colors, typography, divider spacing, charts, comparison
tables, and candidate controls remain unchanged. The two new lines use the
existing state color and ON/K formatting helpers.

### Component status table contract

All five tabs must use the S&P1 component-table presentation contract:

- headers: `지표`, `선택`, `플래그`, `최신 사용값`;
- indicator column left-aligned, selection and flag columns centered, source
  text left-aligned;
- natural table layout with wrapping allowed;
- no fixed `colgroup` widths for the four status columns;
- no `white-space: nowrap` or ellipsis on source-provenance text;
- identical spacer structure between the left and right halves;
- source text is escaped before rendering.

The renderer may be shared or copied locally, but the resulting markup and
visual behavior must match S&P1. This is a presentation-only change. It must
not change the selected component set or component state values.

### Source provenance resolution

The payload must expose a source-provenance row for every displayed component.
The resolver must:

1. use the pinned component-to-source mapping already present in the runtime;
2. for Combo1, resolve the component's required source families directly;
3. for Combo2, expand the child Combo1 mapping and union the underlying
   required sources;
4. choose the oldest effective source value for the display text, including a
   valid weekly source when it is the oldest displayed value;
5. separately compute the confirmed limit using the effective availability
   contract, excluding only authorized cadence carry-forward from the lower
   bound;
6. add cadence and delay notes from existing freshness metadata only.

There must be no fallback from a missing provenance row to the parent
candidate's confirmed basis date. If the mapping cannot be resolved from the
pinned contract, the row is `확인 불가` and the validation gate fails rather
than guessing.

## Validation Plan

### Contract tests

- Confirmed snapshot at a fully fresh fixture equals the provisional snapshot.
- Delayed DBAA/DAAA fixture keeps the last same-date-complete HY/IG proxy in
  provisional mode; it must not mix old corporate data with newer DGS10 data.
- Strict confirmed basis is capped at the latest common required availability.
- Weekly NFCI fixture with a valid carry-forward state does not lower the
  confirmed basis to the NFCI release or availability date.
- The same fixture still displays the NFCI source date and cadence note in the
  component table.
- Provisional basis reaches the latest completed market session when its
  permitted carried state exists.
- Invalid/missing sources produce `PROVISIONAL_UNAVAILABLE`, never Risk-on.
- Empty S&P2 live market input produces `PROVISIONAL_UNAVAILABLE`, never a
  current signal at the Frozen cutoff.
- Hysteresis parity and `final_t1_application_count == 1` hold for both paths.
- Frozen prefix rows and official backtest display metrics remain byte/semantic
  unchanged.

### Tab-level checks

- One selected Combo1 and one selected Combo2 candidate per tab.
- Confirmed/provisional basis, active count, state, execution position, and
  delayed-source metadata are present.
- Current live smoke expectations for the present source snapshot are recorded
  without hard-coding them into runtime logic: S&P1/KOSPI confirmed after the
  weekly carry-forward correction, KOSDAQ/NASDAQ/S&P2 strict basis from their
  daily source limits, and all five provisional bases from the latest permitted
  session.
- Component tables in all five tabs use the S&P1 header, alignment, wrapping,
  and source-provenance semantics.
- No component row contains the generic `잠정 · 확정 YYYY-MM-DD` suffix.
- Arabic display numbering is used for source labels, for example `4.` rather
  than a circled numeral.
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
- A live acquisition failure is being represented as a valid current signal at
  a Frozen cutoff.
- A Combo2 source mapping cannot be resolved without guessing.

## Rollout Order

1. Read-only preflight: record current candidates, source contracts, Frozen
   cutoffs, runtime modes, source status, and basis behavior for all five tabs.
2. Correct the effective confirmed-limit calculation for cadence-carry sources
   without changing indicator calculations or provisional source values.
3. Add source-provenance resolution for Combo1 and expanded Combo2 children.
4. Replace the three fixed-width component table renderers with the S&P1 table
   presentation contract.
5. Make S&P2 live acquisition failure explicit instead of silently rendering
   the Frozen cutoff as a current signal.
6. Preserve and verify the two-line current-state display in all five tabs.
7. Run focused parity, freshness, provenance, table-layout, and fallback tests;
   inspect the final diff and deploy-path smoke output.
8. Stop for user review before commit, push, or deployment unless the user has
   separately approved delivery.

## Execution Approval

On 2026-09-09, the user approved implementation and requested commit and push
after the scoped validation succeeds. This approval supersedes only the final
review stop in the rollout order; every semantic and safety constraint above
remains unchanged.
