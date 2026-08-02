# KOSPI Macro5 D1-C3B.2V Result

## Gate

PASS_KOSPI_MACRO5_D1C3B2V_COMPACT_STATUS_TABLE_WIDTH_READY_FOR_B2

## Scope

- Macro4/Macro5 current status rows now share the same compact two-line structure.
- Active component name lists were removed from the current flag summary.
- Execution guidance is displayed as a compact sentence: execution state plus today's transition.
- Macro5 fresh-session and invalid-session default preset resolves to the unique `[조합2] Main`.
- Macro4/Macro5 Combo1/Combo2 backtest tables share the same fixed colgroup, table layout, minimum width, and horizontal overflow behavior.

## Guardrails

- Chart builders were not changed.
- KOSPI runtime, page adapter, assets, source loaders, and signal calculation logic were not changed.
- No git commit, push, or deploy was performed in this step.

## Validation

- `python3 -m py_compile technical_signal_dashboard.py`
- `python3 -m pytest -q tests/test_kospi_macro5_d1c3b2v_compact_status_table_width.py tests/test_kospi_macro5_d1c3b2r_visual_parity.py tests/test_kospi_macro5_d1c3b2t_backtest_table.py tests/test_kospi_macro5_d1c3b2_structure_table_ui.py tests/test_kospi_macro5_d1c3b2u_state_label_table_fix.py`

Full validation is recorded in the final assistant report for this run.
