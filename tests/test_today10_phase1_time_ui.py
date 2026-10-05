from __future__ import annotations

import pandas as pd

from dashboard_timepoints import candidate_history_rows_at_offsets, history_rows_at_offsets, risk_state_short_label


def test_timepoint_selector_uses_valid_trading_rows_at_or_before_candidate_basis() -> None:
    dates = pd.bdate_range("2026-01-05", periods=27)
    history = pd.DataFrame({
        "candidate_id": "candidate-a",
        "date": dates,
        "active_count": range(len(dates)),
        "raw_risk_state": [index % 2 for index in range(len(dates))],
        "valid_signal": True,
    })
    history.loc[history.index.isin([4, 25]), "valid_signal"] = False
    history = pd.concat([
        history,
        pd.DataFrame([{
            "candidate_id": "candidate-a",
            "date": dates[-1] + pd.offsets.BDay(1),
            "active_count": 99,
            "raw_risk_state": 1,
            "valid_signal": True,
        }]),
    ], ignore_index=True)

    basis = dates[-1]
    actual = candidate_history_rows_at_offsets(
        history,
        "candidate-a",
        basis,
        offsets=(21, 10, 5, 0),
        valid_col="valid_signal",
    )
    eligible = history.loc[history["date"].le(basis) & history["valid_signal"]].sort_values("date")

    assert {offset: row["date"] for offset, row in actual.items()} == {
        offset: eligible.iloc[-offset - 1]["date"] for offset in (21, 10, 5, 0)
    }
    assert all(row["active_count"] != 99 for row in actual.values())


def test_timepoint_selector_falls_back_to_runtime_valid_column_and_keeps_candidate_isolation() -> None:
    dates = pd.bdate_range("2026-03-02", periods=23)
    history = pd.DataFrame({
        "candidate_id": ["a"] * 23 + ["b"] * 23,
        "date": list(dates) * 2,
        "active_count": list(range(23)) + list(range(100, 123)),
        "valid": [True] * 22 + [False] + [True] * 23,
    })
    a = candidate_history_rows_at_offsets(history, "a", dates[-1], offsets=(21, 10, 5, 0), valid_col="valid_signal")
    b = candidate_history_rows_at_offsets(history, "b", dates[-1], offsets=(21, 10, 5, 0), valid_col="valid_signal")

    assert a[0] is not None and a[0]["active_count"] == 21
    assert b[0] is not None and b[0]["active_count"] == 122
    assert a[21] is not None and b[21] is not None
    assert a[21]["active_count"] != b[21]["active_count"]


def test_risk_label_uses_only_authoritative_binary_values() -> None:
    assert risk_state_short_label(0) == "R-on"
    assert risk_state_short_label(1) == "R-off"
    assert risk_state_short_label(False) == "R-on"
    assert risk_state_short_label(True) == "R-off"
    assert risk_state_short_label(None) == "R-계산 불가"
    assert risk_state_short_label(2) == "R-계산 불가"
    assert risk_state_short_label("Risk-off") == "R-계산 불가"


def test_single_history_selector_handles_missing_and_short_histories() -> None:
    dates = pd.bdate_range("2026-04-01", periods=6)
    history = pd.DataFrame({"date": dates, "value": range(6)})
    actual = history_rows_at_offsets(history, dates[-1], offsets=(21, 10, 5, 0))

    assert actual[21] is None
    assert actual[10] is None
    assert actual[5]["value"] == 0
    assert actual[0]["value"] == 5
    assert all(value is None for value in history_rows_at_offsets(history, "not-a-date").values())
