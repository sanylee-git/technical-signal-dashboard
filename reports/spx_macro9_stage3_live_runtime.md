# S&P Macro9 Stage 3 - Proxy-only Live Runtime

`PASS_SPX_MACRO9_STAGE3_LIVE_RUNTIME_VALIDATED`

## Scope

- Added only S&P Macro9 dashboard-owned live assets and runtime modules.
- Existing tabs, research artifacts, Frozen Stage 2 assets, UI, and official display metrics were not modified.
- Runtime dependency is `DASHBOARD_OWNED_ASSETS_ONLY` after the one-way asset build.

## Contract

- Benchmark and signal market: `^GSPC`.
- HY proxy: `DBAA - DGS10`, same-date inner join, then one eligible S&P session availability.
- IG proxy: `DAAA - DGS10`, same-date inner join, then one eligible S&P session availability.
- Credit stress: negative mean of clipped 252-day z-scores for HY proxy, NFCI, and VIX; all three are required.
- Direct ICE OAS, source stitching, level shifts, interpolation, and raw fill are not present in the runtime.
- Combo2 consumes `CHILD_COMBO1_RAW_RISK_STATE`; final T+1 is applied exactly once.
- `T10Y2Y` and `T10Y3M` are retained as the exact research inputs. VIX3M retains the Cboe native latest-source lineage.

## Frozen Prefix Parity

- Selected Core15 raw state versus Stage 2 reference: `mismatch 0` across 52 required Core candidates.
- Final Combo1 official T+1 versus Stage 2 reference: `mismatch 0` across 5 candidates.
- Final Combo2 official T+1 versus Stage 2 reference: `mismatch 0` across 5 candidates.
- Frozen performance metrics remain the existing `final10_frozen_replay_metrics.parquet`; live state never overwrites them.

## Live Behavior

- Live tail is append-only after `2026-08-21`.
- Source observation date remains separate from S&P calculation/basis date.
- A required stale or invalid source yields no new tail; invalid is never converted to Risk-on and no gap is bridged.
- Fixed three-session fixture: basis date `2026-08-26`, tail rows `3`, Frozen rows overwritten `0`, Final10 calculable `10/10`.
- Actual provider smoke at execution time: basis date `2026-09-04`, tail rows `10`, Final10 calculable `10/10`.

## Verification

- `python3 -m py_compile spx_macro9_runtime/*.py tools/build_spx_macro9_live_assets.py`: PASS
- `pytest -q tests/test_spx_macro9_frozen_replay.py tests/test_spx_macro9_live_runtime.py`: PASS (`5 passed`)
- `git diff --check`: PASS

## Stage Boundary

Stage 3 is complete. There is no Streamlit tab, UI renderer, cache/session/widget key, or deployment change yet. The first point at which the user can see S&P지표2 in the dashboard is Stage 4 UI wiring.
