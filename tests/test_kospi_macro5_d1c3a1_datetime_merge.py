from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kospi_macro5_runtime.live_availability import align_to_kospi_calendar, normalize_daily_merge_key


def _datetime_index(unit: str, values: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(np.array(values, dtype=f"datetime64[{unit}]"))


@pytest.mark.parametrize(
    ("calendar_unit", "series_unit"),
    [
        ("us", "s"),
        ("s", "us"),
        ("ns", "us"),
        ("ns", "ns"),
    ],
)
def test_align_to_kospi_calendar_normalizes_daily_merge_key_units(calendar_unit: str, series_unit: str) -> None:
    calendar = _datetime_index(calendar_unit, ["2026-07-23", "2026-07-24", "2026-07-27"])
    series = pd.Series(
        [10.0, 11.0, 12.0],
        index=_datetime_index(series_unit, ["2026-07-23", "2026-07-24", "2026-07-27"]),
    )

    out = align_to_kospi_calendar(calendar, series, "probe", 0)

    assert str(out["date"].dtype) == "datetime64[ns]"
    assert str(out["available_date"].dtype) == "datetime64[ns]"
    assert str(out["observation_date"].dtype) == "datetime64[ns]"
    assert len(out) == 3
    assert out["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-23", "2026-07-24", "2026-07-27"]
    assert out["probe"].tolist() == [10.0, 11.0, 12.0]
    assert int(out["date"].duplicated().sum()) == 0


def test_pandas_raw_merge_asof_reproduces_cloud_dtype_error_without_normalization() -> None:
    left = pd.DataFrame({"date": _datetime_index("us", ["2026-07-24"])})
    right = pd.DataFrame({"available_date": _datetime_index("s", ["2026-07-24"]), "value": [1.0]})

    with pytest.raises(pd.errors.MergeError, match="incompatible merge keys"):
        pd.merge_asof(left, right, left_on="date", right_on="available_date", direction="backward")

    fixed_left = left.copy()
    fixed_right = right.copy()
    fixed_left["date"] = normalize_daily_merge_key(fixed_left["date"])
    fixed_right["available_date"] = normalize_daily_merge_key(fixed_right["available_date"])
    merged = pd.merge_asof(fixed_left, fixed_right, left_on="date", right_on="available_date", direction="backward")

    assert str(merged["date"].dtype) == "datetime64[ns]"
    assert str(merged["available_date"].dtype) == "datetime64[ns]"
    assert merged["value"].tolist() == [1.0]


def test_normalize_daily_merge_key_handles_mixed_inputs_nat_and_unsorted_dates() -> None:
    values = pd.Series([pd.Timestamp("2026-07-24 15:30:00"), "2026-07-23", None, np.datetime64("2026-07-22", "s")])

    normalized = normalize_daily_merge_key(values)

    assert str(normalized.dtype) == "datetime64[ns]"
    assert normalized.dt.strftime("%Y-%m-%d").tolist()[:2] == ["2026-07-24", "2026-07-23"]
    assert pd.isna(normalized.iloc[2])
    assert normalized.iloc[3] == pd.Timestamp("2026-07-22")
    assert len(normalized) == len(values)
