# KOSPI Macro5 D1-C3A Result

- Gate: PASS_KOSPI_MACRO5_D1C3A_MINIMAL_LIVE_PAGE_WIRING_READY_FOR_UI_FINISH
- Scope: Minimal Macro5 page wiring only
- Live loader: connected only inside `render_macro5_kospi_section`
- Probe work: not changed
- New source/contract/asset: none
- Final9 candidates: unchanged
- Frozen performance/chart: unchanged
- Live state replacement: basis date, raw state, T+1, active count, state start/duration, freshness fields

## Smoke

- Source count: 11
- Source reachable count: 11
- Final9 rows: 9
- Combo1 rows: 4
- Combo2 rows: 5
- Calculable rows: 9
- Freshness-qualified rows: 9
- Risk-off rows: 9
- Expected latest KRX session: 2026-07-31
- Page adapter vs probe candidate mismatch: 0
- Streamlit local startup: PASS

## Tests

- `python3 -m py_compile technical_signal_dashboard.py kospi_macro5_runtime/*.py`: PASS
- Existing related pytest in clean worktree: 13 passed

## Status

- Shadow mode: true
- Official operating model: false
- Actual trading ready: false
