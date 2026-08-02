# KOSPI Macro5 D1-C3B.2T Result

## Gate

`PASS_KOSPI_MACRO5_D1C3B2T_BACKTEST_TABLE_COMPLETE_READY_FOR_B2`

Macro5 backtest comparison tables were completed using only existing Frozen assets:

- Final9 candidate metrics
- Final9 reference signal history
- Final9 T+1 position history
- Frozen KOSPI benchmark close history

No chart, signal, candidate, K/L, runtime, availability, freshness, or page adapter logic was changed.

## Table Contract

Both `조합2` and `조합1` tables now use the same 10-column structure:

1. 역할 / 후보
2. 10Y 자산
3. 전체 자산
4. 전체 CAGR
5. 10Y MDD
6. 전체 MDD
7. 전체 Risk-off
8. 전체 Cycle
9. 짧은 Cycle
10. 현재

`20Y` labels are not used because the official KOSPI Frozen evaluation window is shorter than 20 years.

## Evaluation Windows

Resolved from Frozen benchmark/reference data:

- Official full window: `2008-04-01 ~ 2026-07-28`
- Trailing 10Y window: `2016-07-28 ~ 2026-07-28`
- Live tail after the Frozen end is not included in performance statistics.
- Live data is used only in the `현재` column.

## B&H Row

Each table appends one final `KOSPI 홀드` row:

- `조합2`: 5 candidates + 1 KOSPI hold row
- `조합1`: 4 candidates + 1 KOSPI hold row

The KOSPI hold row shows:

- 10Y asset
- full asset
- full CAGR
- 10Y MDD
- full MDD
- full Risk-off = `0.0%`
- full Cycle = `-`
- short Cycle = `-`
- current = `-`

Candidate rows show Macro4-style green/gray ratio spans for:

- 10Y asset vs KOSPI hold
- full asset vs KOSPI hold
- 10Y MDD vs KOSPI hold
- full MDD vs KOSPI hold

## Parity

Existing Frozen metrics are displayed directly for:

- full CAGR
- full MDD
- full Risk-off

Read-only derived display stats are computed from stored Frozen T+1 positions and KOSPI close for:

- 10Y asset
- full asset
- 10Y MDD
- full cycle count
- short cycle count
- KOSPI hold row

No model signals are regenerated.

## Invariance

- Logic mismatch: `0`
- Signal mismatch: `0`
- Candidate mismatch: `0`
- T+1 mismatch: `0`
- Active-count mismatch: `0`
- Frozen CAGR mismatch: `0`
- Frozen MDD mismatch: `0`
- Frozen Risk-off mismatch: `0`
- New source: `0`
- New candidate: `0`
- New dependency: `0`
- Deleted file: `0`

Protected functions remained unchanged:

- `_macro5_kospi_build_main_chart`
- `_macro5_kospi_build_component_chart`
- `render_macro6_proxy_final_section`
- `_build_macro6_backtest_panel`
- `_make_macro6_combo_chart_from_snapshot`
- `_build_macro6_component_chart`
- `_build_macro6_indicator_chart`

## Verification

- `python3 -m py_compile technical_signal_dashboard.py`: PASS
- `python3 -m pytest tests/test_kospi_macro5_d1c3b2_structure_table_ui.py tests/test_kospi_macro5_d1c3b2r_visual_parity.py tests/test_kospi_macro5_d1c3b2t_backtest_table.py -q`: PASS
- `python3 -m pytest -q`: PASS, 38 passed, 2 existing pandas FutureWarnings
- `python3 -m compileall -q technical_signal_dashboard.py kospi_macro5_runtime tests`: PASS
- `python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8530 --browser.gatherUsageStats false`: startup PASS
- `curl -I http://localhost:8530/`: HTTP 200
