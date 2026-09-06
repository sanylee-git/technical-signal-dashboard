# S&P지표2 Stage 2 - Frozen Asset Build and Direct Replay

`PASS_SPX_MACRO9_STAGE2_FROZEN_REPLAY_PARITY`

## Scope

- Dashboard-owned assets only: `spx_macro9_assets/`
- New runtime namespace only: `spx_macro9_runtime/`
- Existing tabs, existing runtime, research artifacts: not modified.
- Network calls: 0 during build validation and replay validation.

## Frozen Asset Contract

- Proxy-only Core15 canonical bank was SHA-verified before extraction.
- Direct ICE OAS, stitch, level shift, fill/interpolation: not included.
- Core candidates retained: 52.
- Final Combo2 child Combo1 raw histories retained: 27.
- Final10 membership: Combo1 5 + Combo2 5, exact Stage 1 IDs/K/L/child mappings.
- Runtime does not reference `macro_dashboard_snp`; only the one-time asset builder does.

## Period Semantics Preserved

The research artifacts use two frozen metric calendars. They are deliberately
kept separate rather than relabelled as one common period.

| Family | Frozen state/metric period | Rows |
|---|---|---:|
| Final Combo1 | Development: 2013-10-03 to 2026-08-21 | 3,240 |
| Final Combo2 | Official: 2008-04-01 to 2026-08-21 | 4,628 |

The later UI stage must display these stored metric semantics as-is. Live tail
must not overwrite either frozen metric set.

## Direct Replay Results

- Core raw -> Core T+1 alignment: 52/52 exact.
- Core raw -> Final Combo1 raw -> official T+1: 5/5 exact state parity.
- Child Combo1 full source-history raw -> Final Combo2 raw -> official T+1: 5/5 exact state parity.
- Final10 performance parity: CAGR, MDD, Calmar, total return, raw Risk-off ratio, raw cycle count, Short20 ratio, and execution transition count: 10/10 exact.
- Invalid component treated as Risk-on: 0. Every selected frozen Core validity mask is all-valid on its pinned calendar.
- Final T+1 application count: 1. Combo2 input semantics: `CHILD_COMBO1_RAW_RISK_STATE`.

## Validation

- `pytest -q tests/test_spx_macro9_frozen_replay.py`: `2 passed`
- `python3 -m py_compile spx_macro9_runtime/frozen_replay.py tools/build_spx_macro9_frozen_assets.py tests/test_spx_macro9_frozen_replay.py`: PASS
- `git diff --check`: PASS

## Next Boundary

Stage 3 may add only an independent S&P Proxy-only live-tail runtime. Frozen
assets and official metric display fields are immutable; no UI work begins in
this stage.
