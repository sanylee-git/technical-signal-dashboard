# Confirmed/Provisional Signal UI Alignment Addendum

## Purpose

Follow up on the implemented confirmed/provisional signal policy without
changing the original operating contract. This addendum aligns the five tabs'
status wording and component freshness display:

- S&P1 / Macro6
- KOSPI / Macro5
- KOSDAQ / Macro7
- NASDAQ / Macro8
- S&P2 / Macro9

The original implementation plan and commit remain historical records and are
not rewritten.

## Verified Findings

1. KOSDAQ, NASDAQ, and S&P2 currently render the confirmed/provisional session
   gap on a separate third line.
2. The desired placement is on the provisional line:

   ```text
   잠정신호: 기준일 YYYY-MM-DD · 현재 플래그 ON/K · 상태 ... · 확정 기준과 N 거래일 차이
   ```

3. S&P1 and KOSPI do not have one consistent local-code path for the session
   gap. The shared Macro6/KOSPI status helper must receive an explicit
   market-session gap instead of silently omitting it. A screenshot/deployed
   revision showing a different KOSPI result must not be treated as source
   code evidence until the deployed revision is matched.
4. S&P1 and KOSPI component tables already expose source-aware latest-use text,
   including delay or weekly cadence details.
5. KOSDAQ, NASDAQ, and S&P2 component tables currently use component-history
   dates only. Those dates can represent the provisional calculation date and
   do not identify the oldest source or a carried delayed value.
6. KOSDAQ's component-table latest-date header alignment is inconsistent with
   the centered headers used by the other cloned tables.

## Scope

Allowed:

- Move the existing session-gap text into the provisional signal line.
- Add the same session-gap calculation to S&P1 and KOSPI using trading-session
  dates, not calendar-day subtraction.
- Expose existing confirmed basis/source provenance already available in each
  runtime payload to the KOSDAQ/NASDAQ/S&P2 component tables.
- Render source-aware labels such as `latest used`, `weekly update`, `delay`,
  or `provisional carry` without adding provider calls.
- Center the component-table headers consistently.
- Add focused UI/payload tests and a validation report.

Forbidden:

- Changing indicator formulas, candidate definitions, K/L, hysteresis, T+1,
  stage mapping, model state, official metrics, charts, tables' row structure,
  or data-source policy.
- Treating a provisional calculation date as proof that every source was fresh
  on that date.
- Adding network calls, fallback sources, new cache behavior, or new source
  data.
- Modifying Frozen assets, prior reports, unrelated tabs, or unrelated dirty
  worktree files.

## Display Contract

For every selected candidate:

```text
확정신호: confirmed basis · state
잠정신호: provisional basis · state · 확정 기준과 N 거래일 차이
현재 상태 시작일 · 지속 거래일 · 상태 구간 수익률 · 실행 · 전환
```

The third line remains the existing provisional-state duration/return line.
The gap is omitted when it is zero. The gap is counted from the tab's actual
market-session calendar, never from elapsed calendar days.

For component status tables:

- The displayed date must be labelled according to its meaning.
- A provisional carried state must not be shown as an independently fresh
  source observation.
- Where source provenance exists, show the oldest required used value and its
  cadence/delay detail.
- Where only a candidate/component confirmed basis is available, show that
  basis as provenance and do not fabricate a source-specific label.
- Combo2 child rows remain child Combo1 state rows; they must not be given
  fabricated Core indicator source dates.

## Implementation Order

1. Read-only baseline and current diff audit.
2. Update the common status renderers so the session gap is passed explicitly
   and rendered on the provisional line.
3. Add the equivalent gap input for S&P1 and KOSPI from existing session/history
   data.
4. Add source/basis display metadata to KOSDAQ, NASDAQ, and S&P2 presentation
   payloads and wire their component tables to it.
5. Center all component-table headers while preserving values, columns, and
   widths.
6. Run focused tests and inspect the final diff for zero calculation/model
   changes.

## Required Gates

- All five tabs contain the same two-line confirmed/provisional structure.
- No separate third-line session-gap text remains.
- S&P1, KOSPI, KOSDAQ, NASDAQ, and S&P2 use market-session gap counts.
- KOSDAQ, NASDAQ, and S&P2 component tables distinguish provisional dates
  from source freshness where the payload can prove it.
- Existing S&P1/KOSPI source-aware labels remain unchanged.
- Frozen prefix and official backtest metrics are unchanged.
- Candidate/K/L/T+1/model-state parity is unchanged.
- No new provider/network request is introduced.
- `py_compile`, focused runtime/UI tests, and `git diff --check` pass.

Success gate:

`PASS_CONFIRMED_PROVISIONAL_SIGNAL_UI_ALIGNMENT_ALL_FIVE_TABS`

Commit/push is performed only after implementation and validation are complete
and explicitly requested for this addendum.
