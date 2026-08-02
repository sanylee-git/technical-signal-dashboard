# KOSPI Macro5 D1-C3A.1 Datetime Merge-Key Compatibility Fix

## Gate

PASS_KOSPI_MACRO5_D1C3A1_DATETIME_MERGE_COMPATIBILITY_FIXED

## Scope

- Commit base: cb09861
- UI changed: false
- technical_signal_dashboard.py changed: false
- Macro4 changed: false
- Macro6 changed: false
- Probe changed: false
- New feature: 0
- New Secret: 0
- New query parameter: 0
- New dependency: 0
- Deleted files: 0
- Commit/push/deploy: false

## Root Cause

- Actual failing location: `kospi_macro5_runtime/live_availability.py::align_to_kospi_calendar`
- Failing operation: `pd.merge_asof(base, available, left_on="date", right_on="available_date")`
- Reproduced incompatible keys:
  - left `date`: `datetime64[us]`
  - right `available_date`: `datetime64[s]`
- Fix: normalize daily merge keys symmetrically to timezone-naive midnight `datetime64[ns]` before merge.

## Regression

- datetime64[us] + datetime64[s] reproduction: PASS
- datetime64[s] + datetime64[us]: PASS
- datetime64[ns] + datetime64[us]: PASS
- datetime64[ns] + datetime64[ns]: PASS
- mixed Python date/string/NaT input: PASS
- unsorted input calendar date preservation: PASS

## Data Meaning Preservation

- Frozen rows: 7,292
- Transformed rows: 7,295
- Expected row change from live tail: 3
- Unexpected row change: 0
- Frozen period: 1996-12-11 ~ 2026-07-28
- Transformed period: 1996-12-11 ~ 2026-07-31
- Live tail start: 2026-07-29
- Calendar date shift: 0
- New duplicate dates: 0
- Frozen overwrite count: 0
- Output `date` dtype: `datetime64[ns]`

## Live Smoke

- Source count: 11 / 11
- Source reachable: 11 / 11
- Final9 rows: 9 / 9
- Combo1 rows: 4
- Combo2 rows: 5
- Calculable: 9 / 9
- Freshness-qualified: 9 / 9
- Risk-off count: 9 / 9
- Basis date: 2026-07-31

## Parity

Validation compared `page_adapter.load_macro5_live_page_data()` against `cloud_probe.run_cloud_probe()` output for semantic candidate fields only.

- candidate ID mismatch: 0
- basis date mismatch: 0
- raw mismatch: 0
- T+1 mismatch: 0
- active-count mismatch: 0
- freshness-qualified mismatch: 0

## Verification Commands

- `python3 -m py_compile kospi_macro5_runtime/*.py technical_signal_dashboard.py`: PASS
- `python3 -m compileall -q kospi_macro5_runtime tests`: PASS
- `python3 -m pytest -q tests/test_kospi_macro5_d1c3a1_datetime_merge.py`: PASS, 6 passed
- Related existing tests found and run:
  - `tests/test_kospi_macro5_d1c2b_cloud_probe_bridge.py`
  - `tests/test_kospi_macro5_d1c3a_page_wiring.py`
  - `tests/test_kospi_macro5_d1c3a1_datetime_merge.py`
- Related pytest result: PASS, 11 passed
- Streamlit local startup: PASS at `http://127.0.0.1:8771`

## Status

AWAITING_USER_APPROVAL_KOSPI_MACRO5_D1C3A1_COMMIT_PUSH
