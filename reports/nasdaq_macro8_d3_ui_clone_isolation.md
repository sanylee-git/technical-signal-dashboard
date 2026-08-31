# NASDAQ Macro8 Stage 4 UI Clone + Isolation

Gate: `PASS_NASDAQ_MACRO8_D3_UI_CLONE_ISOLATION_READY`

## Implemented

- Added the independent `macro8_nasdaq` page entry and `🇺🇸 나스닥지표` selector.
- Added a NASDAQ-only renderer using the KOSDAQ page's section order, typography,
  divider spacing, table layout, status summary, expanders, and Plotly styling.
- The page consumes one `FROZEN_ONLY` presentation payload. Candidate, period,
  component, and auxiliary-line UI changes reuse that payload.
- Combo1 detailed charts consume existing Core15 chart-ready Frozen fields.
  Combo2 detailed charts consume child Combo1 raw-state history and NASDAQ 100
  benchmark only.
- The all-period chart start is the official `2008-04-01` evaluation boundary;
  every chart end is the candidate basis date `2026-08-21`.

## Contract Checks

- Final20: 20/20 displayed; no selection or re-ranking.
- Runtime: Frozen-only; provider/network calls 0.
- Proxy policy: HY = DBAA - DGS10, IG = DAAA - DGS10; direct OAS used 0.
- KOSPI/KOSDAQ runtime imports in NASDAQ UI/presentation modules: 0.
- UI-side indicator, hysteresis, T+1, validity, or freshness calculation: 0.

## Validation

- `python3 -m py_compile` for launcher, Macro8 renderer/runtime, and tests: PASS.
- NASDAQ Frozen replay/runtime/UI regression suite: 8 passed.
- Streamlit renderer smoke: PASS.
- Streamlit dashboard `main(page="macro8_nasdaq")` entry smoke: PASS.

## Self Feedback

Presentation-payload assembly initially attempted to reinsert an existing
`component_id` field, and the table expected a display `asset` field absent
from the source metric schema. Both were presentation-layer contract issues,
corrected by retaining the source component ID and exposing `asset = 100 *
(1 + total_return)` as a display-only field. Frozen states, formulas, T+1,
candidate membership, and official performance metrics were unchanged.
