from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nasdaq_macro8_runtime.frozen_replay import performance_calendar, replay_core, replay_final20


FROZEN = ROOT / "nasdaq_macro8_assets" / "frozen"


def test_frozen_core15_and_final20_parity() -> None:
    panel = pd.read_parquet(FROZEN / "frozen_nasdaq_core15_input.parquet")
    registry = pd.read_parquet(FROZEN / "core15_selected_candidate_registry.parquet")
    reference_state = pd.read_parquet(FROZEN / "core15_selected_reference_risk_state.parquet")
    reference_valid = pd.read_parquet(FROZEN / "core15_selected_reference_valid_signal.parquet")
    final20 = pd.read_csv(ROOT / "nasdaq_macro8_assets" / "nasdaq_macro8_final20.csv")
    children = pd.read_csv(ROOT / "nasdaq_macro8_assets" / "nasdaq_macro8_combo2_child_mapping.csv")

    core = replay_core(panel, registry)
    assert len(core) == 48
    for candidate_id in registry["candidate_id"].astype(str):
        assert np.array_equal(reference_state[candidate_id].fillna(-1).to_numpy(dtype=np.int8), core[candidate_id]["raw"])
        assert np.array_equal(reference_valid[candidate_id].to_numpy(dtype=np.int8).astype(bool), core[candidate_id]["valid"])

    actual = replay_final20(panel, final20, children, core)
    expected = final20.set_index("candidate_id")
    assert len(actual) == 20
    for row in actual.itertuples(index=False):
        expected_row = expected.loc[row.candidate_id]
        assert abs(row.cagr - float(expected_row.cagr)) <= 1e-12
        assert abs(row.mdd - float(expected_row.mdd)) <= 1e-12
        assert abs(row.calmar - float(expected_row.calmar)) <= 1e-12


def test_performance_calendar_owns_a_writable_return_copy_under_copy_on_write() -> None:
    panel = pd.read_parquet(FROZEN / "frozen_nasdaq_core15_input.parquet")
    previous = pd.options.mode.copy_on_write
    pd.options.mode.copy_on_write = True
    try:
        _dates, _mask, _start, _end, returns = performance_calendar(panel)
    finally:
        pd.options.mode.copy_on_write = previous
    assert returns.flags.writeable
    assert returns[0] == 0.0
