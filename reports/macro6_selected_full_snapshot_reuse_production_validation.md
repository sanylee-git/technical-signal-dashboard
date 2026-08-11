# Macro6 Selected Full Snapshot Reuse Production Validation

Final Gate: PASS_MACRO6_SELECTED_FULL_SNAPSHOT_REUSE_PRODUCTION_LOCAL_VALIDATED

Generated: 2026-08-11 KST

## 1. Git Baseline

| Item | Value |
|---|---|
| branch | `main` |
| start HEAD | `49122f978925a0ef5baba522b3cb29bd58d74ced` |
| start origin/main | `49122f978925a0ef5baba522b3cb29bd58d74ced` |
| latest commit | `49122f9 Add Macro5 FRED diagnostic reports` |
| required ancestor | `5062d21 Parallelize Macro5 FRED source fetches safely` |

Allowed pre-existing untracked reports:

- `reports/macro6_cold_bottleneck_analysis.md`
- `reports/macro6_cold_timing_trace.md`
- `reports/macro6_selected_detail_reuse_parity_pilot.md`

## 2. Pilot Basis

The preceding repo-outside diagnostic pilot passed:

`PASS_MACRO6_SELECTED_DETAIL_PARTIAL_REUSE_PARITY_PILOT`

Measured pilot result:

| Metric | Baseline | Reuse | Saving |
|---|---:|---:|---:|
| post-summary detail median | 7.273s | 2.447s | 4.826s |
| total compute median | 33.347s | 28.465s | 4.882s |

Proven exact duplicate:

| Function | Candidate |
|---|---|
| `_compute_macro6_preset_signal_frame` | `m8_8112998890601066` |

The pilot did not prove component chart or status panel reuse. Those paths are left
untouched by this production patch.

## 3. Production Change

Modified production file:

- `technical_signal_dashboard.py`

Changed lines:

- `8478-8573`: Macro6 selected signal reuse sidecar and exact identity helpers
- `8822-8862`: selected full snapshot exact-match reuse with compute fallback
- `8869-8906`: summary calculation captures only the selected candidate signal
- `8909-8940`: summary-map calculation selects one capture target

Modified test file:

- `tests/test_macro6_phase2e_summary_snapshot.py`

Added tests:

- exact-match selected snapshot reuse
- identity mismatch fallback
- component chart/status separate-path preservation

## 4. Reuse Boundary

The production patch reuses only this result:

```text
_compute_macro6_preset_signal_frame(
    spx_s,
    benchmark_name,
    preset_cfg,
    sync_bucket,
    source_mode=None,
)
```

Reuse identity includes:

- candidate key / combo id
- kind
- benchmark name
- sync bucket
- source mode
- K/L
- selected indicators
- components
- cfgs
- component cfgs
- S&P benchmark series semantic fingerprint

If the exact identity is absent, the snapshot path calls the original
`_compute_macro6_preset_signal_frame(...)` path.

No candidate id is hardcoded in production code. The default selected candidate
from the pilot is just the measured example.

## 5. Memory / Summary Scope

The patch does not put all 11 full candidate frames into `summary_map`.

Instead:

- summary display payload remains compact
- one selected candidate signal result is captured in a small sidecar store
- the store is capped at 8 identities
- reused DataFrames are returned as defensive deep copies

This keeps the optimization narrow and avoids turning the all-candidate summary
map into a heavy full-snapshot cache.

## 6. Untouched Areas

No semantic changes were made to:

- component chart calculation
- status panel calculation
- provider/source logic
- Yahoo/FRED calls
- timeout/retry/TTL
- freshness / availability / fallback
- K/L
- hysteresis
- market-stage
- proxy-only definitions
- UI/design/layout/text
- Macro5

## 7. Fixed-Input Reference

Before patch, a fixed-input reference was stored outside the repo:

- `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_selected_full_snapshot_reuse_reference_20260811.pkl`
- `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_selected_full_snapshot_reuse_reference_20260811.json`

After patch, the same fixed source inputs were replayed:

- `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_selected_full_snapshot_reuse_after_20260811.json`

Fixed-input result:

| Check | Result |
|---|---|
| summary hash | PASS |
| selected summary hash | PASS |
| full snapshot hash | PASS |
| main chart hash | PASS |
| main event hash | PASS |
| status hash | PASS |
| Combo2 backtest panel hash | PASS |
| Combo1 backtest panel hash | PASS |

Patched fixed-input call count:

| Phase | `_compute_macro6_preset_signal_frame` calls |
|---|---:|
| summary | 11 |
| selected snapshot | 0 |

Patched fixed-input selected snapshot elapsed:

- `0.154s`

## 8. Live Smoke

Repo-outside live smoke:

- `/Users/ibaeksan/Documents/프로젝트/_diagnostics/macro6_selected_full_snapshot_reuse_live_smoke_20260811.json`

Observed:

| Field | Value |
|---|---:|
| selected key | `macro6_combo2_1` |
| selected candidate | `m8_8112998890601066` |
| basis date | 2026-08-10 |
| S&P latest | 2026-08-10 |
| selected state | Risk-on / off-cycle |
| selected on count | 1 |
| summary count | 11 |
| selected snapshot duplicate calls | 0 |
| selected snapshot elapsed | 0.191s |

No latest/freshness/source regression was observed.

## 9. Local Streamlit Smoke

Started local Streamlit server:

```text
python3 -m streamlit run technical_signal_dashboard.py --server.headless true --server.port 8561 --server.address 127.0.0.1
```

Health endpoint:

```text
ok
```

The server was stopped after the smoke check.

## 10. Tests

Commands:

```text
python3 -m py_compile technical_signal_dashboard.py
PYTHONPATH=. pytest -q tests/test_macro6_phase2e_summary_snapshot.py tests/test_macro6_phase2c_source_reuse.py tests/test_macro6_phase2f_detail_chart_cache.py
PYTHONPATH=. pytest -q tests/test_kospi_macro5_d1c3b2_structure_table_ui.py tests/test_kospi_macro5_d1c3b2r_visual_parity.py tests/test_kospi_macro5_d1c3b2t_backtest_table.py tests/test_kospi_macro5_d1c3b2v_compact_status_table_width.py
PYTHONPATH=. pytest -q
```

Results:

| Test | Result |
|---|---|
| py_compile | PASS |
| Macro6 targeted tests | 12 passed |
| Macro4/Macro5/Macro6 UI regression targeted tests | 32 passed |
| full pytest | 102 passed, 19 warnings |

Warnings were existing pandas/yfinance future warnings, not failures.

## 11. Performance Summary

Pilot fixed-input median:

| Metric | Before | After | Saving |
|---|---:|---:|---:|
| post-summary detail | 7.273s | 2.447s | 4.826s |
| total compute | 33.347s | 28.465s | 4.882s |

Patched fixed-input snapshot-only validation:

| Metric | Value |
|---|---:|
| selected snapshot duplicate calls | 0 |
| selected snapshot elapsed | 0.154s |

The production patch removes the proven selected full snapshot duplicate. Component
chart and status costs remain, by design.

## 12. Semantic Diff Audit

Allowed diff:

- Macro6 selected full snapshot exact duplicate reuse orchestration
- targeted regression tests
- this validation report

Required zero semantic change:

| Area | Result |
|---|---|
| UI/design | 0 |
| data-source/provider | 0 |
| latest/freshness/fallback | 0 |
| K/L/hysteresis/market-stage | 0 |
| chart/status logic | 0 |
| Macro5 | 0 |

## 13. Commit / Push

Commit, push, and deploy were not performed in this step.

Next step may proceed to final diff safety audit, selective commit, push, and Cloud
smoke if the user approves.
