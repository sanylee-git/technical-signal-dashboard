from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class KeyCoverageResult:
    reference: str
    duplicate_reference_keys: int
    duplicate_replay_keys: int
    reference_missing_in_replay: int
    replay_extra_rows: int
    unexplained_extra_rows: int


def _is_valid(value: object) -> bool:
    return bool(value) and not pd.isna(value)


def hysteresis_from_nullable_counts(
    active_count: pd.Series,
    valid: pd.Series,
    k: int,
    l: int,
    *,
    component_count: int | None = None,
    initial_state: bool = False,
) -> pd.DataFrame:
    """K/L hysteresis where invalid rows do not mutate the latent state.

    `risk_state=1` means Risk-off. Invalid rows produce null raw state and no
    start/end events; the next valid row resumes from the previous latent state.
    """

    if l < 0 or k <= 0 or l >= k:
        raise ValueError(f"invalid K/L: K={k}, L={l}")
    if component_count is not None and k > component_count:
        raise ValueError(f"K={k} exceeds component_count={component_count}")
    if len(active_count) != len(valid):
        raise ValueError("active_count and valid must have the same length")

    state = bool(initial_state)
    raw_values: list[int | pd.NA] = []
    start_values: list[int] = []
    end_values: list[int] = []
    valid_values: list[bool] = []
    latent_values: list[int] = []

    for count_value, valid_value in zip(active_count.tolist(), valid.tolist()):
        if not _is_valid(valid_value) or pd.isna(count_value):
            raw_values.append(pd.NA)
            start_values.append(0)
            end_values.append(0)
            valid_values.append(False)
            latent_values.append(int(state))
            continue

        previous = state
        count = int(count_value)
        if not state and count >= k:
            state = True
        elif state and count <= l:
            state = False

        raw_values.append(int(state))
        start_values.append(int((not previous) and state))
        end_values.append(int(previous and (not state)))
        valid_values.append(True)
        latent_values.append(int(state))

    return pd.DataFrame(
        {
            "raw_risk_state": pd.Series(raw_values, index=active_count.index, dtype="Int8"),
            "risk_start_signal": pd.Series(start_values, index=active_count.index, dtype="int8"),
            "risk_end_signal": pd.Series(end_values, index=active_count.index, dtype="int8"),
            "valid_signal": pd.Series(valid_values, index=active_count.index, dtype="bool"),
            "latent_state_after_row": pd.Series(latent_values, index=active_count.index, dtype="int8"),
        },
        index=active_count.index,
    )


def t1_position_from_nullable_raw(raw_risk_state: pd.Series, valid_signal: pd.Series) -> pd.DataFrame:
    """Apply Final T+1 using raw risk state without treating missing as Risk-on."""

    if len(raw_risk_state) != len(valid_signal):
        raise ValueError("raw_risk_state and valid_signal must have the same length")

    position: list[int | pd.NA] = []
    t1_valid: list[bool] = []
    for i in range(len(raw_risk_state)):
        if i == 0:
            position.append(pd.NA)
            t1_valid.append(False)
            continue
        prev_valid = _is_valid(valid_signal.iloc[i - 1])
        prev_raw = raw_risk_state.iloc[i - 1]
        if not prev_valid or pd.isna(prev_raw):
            position.append(pd.NA)
            t1_valid.append(False)
            continue
        position.append(1 - int(prev_raw))
        t1_valid.append(True)

    return pd.DataFrame(
        {
            "t1_position": pd.Series(position, index=raw_risk_state.index, dtype="Int8"),
            "t1_valid": pd.Series(t1_valid, index=raw_risk_state.index, dtype="bool"),
        },
        index=raw_risk_state.index,
    )


def derive_events_from_raw(raw_risk_state: pd.Series, valid_signal: pd.Series | None = None) -> pd.DataFrame:
    valid = raw_risk_state.notna() if valid_signal is None else valid_signal.astype(bool) & raw_risk_state.notna()
    prev = raw_risk_state.shift(1)
    prev_valid = valid.shift(1).astype("boolean").fillna(False).astype(bool)
    start = (valid & (raw_risk_state == 1) & ((~prev_valid) | (prev.fillna(0) == 0))).astype("int8")
    end = (valid & (raw_risk_state == 0) & prev_valid & (prev == 1)).astype("int8")
    return pd.DataFrame(
        {
            "risk_start_signal": start,
            "risk_end_signal": end,
            "valid_signal": valid.astype("bool"),
        },
        index=raw_risk_state.index,
    )


def compare_nullable_values(left: pd.Series, right: pd.Series) -> pd.Series:
    left_na = left.isna()
    right_na = right.isna()
    return (left_na != right_na) | ((~left_na) & (~right_na) & (left.astype("float") != right.astype("float")))


def key_coverage(
    reference: str,
    reference_df: pd.DataFrame,
    replay_df: pd.DataFrame,
    key_cols: Iterable[str],
    *,
    allowed_extra: set[tuple] | None = None,
) -> KeyCoverageResult:
    key_cols = list(key_cols)
    allowed_extra = allowed_extra or set()
    ref_dupes = int(reference_df.duplicated(key_cols).sum())
    replay_dupes = int(replay_df.duplicated(key_cols).sum())
    ref_keys = set(map(tuple, reference_df[key_cols].astype(str).itertuples(index=False, name=None)))
    replay_keys = set(map(tuple, replay_df[key_cols].astype(str).itertuples(index=False, name=None)))
    missing = ref_keys - replay_keys
    extra = replay_keys - ref_keys
    unexplained_extra = extra - allowed_extra
    return KeyCoverageResult(
        reference=reference,
        duplicate_reference_keys=ref_dupes,
        duplicate_replay_keys=replay_dupes,
        reference_missing_in_replay=len(missing),
        replay_extra_rows=len(extra),
        unexplained_extra_rows=len(unexplained_extra),
    )


def evaluate_gate(counts: dict[str, int | str]) -> str:
    hard_fields = [
        "parser_missing_count",
        "compute_missing_count",
        "core_state_mismatch_count",
        "core_start_mismatch_count",
        "core_end_mismatch_count",
        "core_validity_mismatch_count",
        "child_raw_mismatch_count",
        "child_start_mismatch_count",
        "child_end_mismatch_count",
        "final_raw_mismatch_count",
        "final_start_mismatch_count",
        "final_end_mismatch_count",
        "final_t1_mismatch_count",
        "missing_adversarial_fail_count",
        "missing_as_risk_on_count",
        "denominator_shrink_count",
        "latent_state_mutation_on_invalid_count",
        "invalid_t1_zero_substitution_count",
        "reference_missing_key_count",
        "duplicate_key_count",
        "unexplained_extra_count",
        "placeholder_validation_count",
        "hardcoded_gate_result_count",
    ]
    for field in hard_fields:
        value = counts.get(field, 0)
        if isinstance(value, str):
            return "BLOCKED_KOSPI_MACRO5_D1C1A2_GATE_INTEGRITY"
        if int(value) != 0:
            return "BLOCKED_KOSPI_MACRO5_D1C1A2_GATE_INTEGRITY"
    if counts.get("metric_parity_status") != "NOT_EVALUATED_CONTRACT_NOT_BOUND":
        return "BLOCKED_KOSPI_MACRO5_D1C1A2_METRIC_CONTRACT_STATUS"
    return "PASS_KOSPI_MACRO5_D1C1A2_VALIDITY_AND_GATE_INTEGRITY_READY"
