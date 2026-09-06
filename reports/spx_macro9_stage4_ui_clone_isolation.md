# S&P Macro9 Stage 4 — UI Clone + Isolation

## Result

`PASS_SPX_MACRO9_STAGE4_UI_CLONE_ISOLATION`

The dashboard now exposes a separate `S&P지표2` section through the existing
market/macro entry point. The renderer uses the S&P-owned Macro9 runtime and
presentation payload only.

## Fixed contracts

- Final10 display set: Combo1 5개 + Combo2 5개, exact candidate IDs from the
  Stage 1 contract; no reselection or ranking.
- Operational display roles: Combo1 `ff766a24...` / `7b12636f...` as Main1 /
  Main2, and Combo2 `8ed8c962...` / `95cff355...` as Main1 / Main2. This is a
  display-order/role mapping only; candidate definitions and metrics remain
  frozen.
- Benchmark: `^GSPC` / S&P 500.
- Proxy-only: `HY = DBAA - DGS10`, `IG = DAAA - DGS10`; direct OAS and source
  stitching are not used.
- Combo2 chart components use child Combo1 raw risk-state history. Combo1
  components use the Core15 chart-ready history.
- Official Frozen metrics remain separate from the appended Live tail.
- Runtime, cache, session, widget, chart, and debug namespaces use `macro9_spx`
  or `spx_macro9` names.

## Validation

- `python3 -m py_compile technical_signal_dashboard.py spx_macro9_ui.py spx_macro9_runtime/*.py`: PASS
- Frozen replay, Live runtime, and Stage 4 payload/isolation tests: 8 passed
- Frozen payload: 10 candidates, 5 Combo1 + 5 Combo2, basis date `2026-08-21`
- Existing UI modules were not modified; the dashboard integration diff only
  adds the new page key, section route, container, import, and renderer call.

Cloud deployment is intentionally not included in Stage 4. The new section is
available in the local dashboard source and becomes available in Cloud only
after the normal commit/push/deploy step.
