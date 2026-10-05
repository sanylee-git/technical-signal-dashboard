from __future__ import annotations

import pytest

from dashboard_role_aware_stage import (
    ROLE_ORDER,
    STAGE_LABELS,
    combine_combo_stages,
    classify_role_combo,
    evaluate_combo,
)
from role_aware_stage_vectors import (
    COMBO_CASES,
    EXPECTED_MERGE_MATRIX,
    ROLE_VECTORS,
    STAGE_CODES,
)


@pytest.mark.parametrize("role_1,role_2,expected_class", ROLE_VECTORS)
def test_all_eleven_canonical_role_combinations(role_1, role_2, expected_class) -> None:
    original = classify_role_combo(role_1, role_2)
    if role_2 is None:
        reversed_pair = classify_role_combo(role_1)
    else:
        reversed_pair = classify_role_combo(role_2, role_1)

    assert original.warning_class == expected_class
    assert reversed_pair.warning_class == expected_class
    assert original.canonical_combo == reversed_pair.canonical_combo
    assert len(original.canonical_combo.split(" + ")) <= 2


@pytest.mark.parametrize("case", COMBO_CASES, ids=lambda case: case["test_id"])
def test_combo_rule_boundaries_for_four_and_five_models(case) -> None:
    result = evaluate_combo(case["metadata"], case["states"])

    assert result.stage == case["expected_stage"]
    assert result.reason_code == case["expected_reason"]
    assert result.model_count == len(case["metadata"])
    assert result.risk_off_count == sum(case["states"].values())
    assert result.early_off + result.meaningful_off + result.hard_core_off == result.risk_off_count
    assert result.label == STAGE_LABELS[result.stage]
    assert (result.stage == "SELL") == ("Risk-off" in result.label)


def test_dual_role_risk_off_candidate_counts_once_and_uses_one_class() -> None:
    metadata = [
        {"candidate_id": "main", "designation": "MAIN", "role_1": "균형형"},
        {"candidate_id": "dual", "designation": "Confirm", "role_1": "보수방어형", "role_2": "추세지속형"},
        {"candidate_id": "early", "designation": "Confirm", "role_1": "보수방어형"},
        {"candidate_id": "core", "designation": "Confirm", "role_1": "공격진입형"},
    ]
    result = evaluate_combo(metadata, {"main": 0, "dual": 1, "early": 0, "core": 0})

    assert result.risk_off_count == 1
    assert (result.early_off, result.meaningful_off, result.hard_core_off) == (0, 0, 1)
    assert result.stage == "WEAK_CAUTION"


def test_a_single_dual_role_h_confirm_is_one_independent_h_vote() -> None:
    metadata = [
        {"candidate_id": "main", "designation": "MAIN", "role_1": "공격진입형"},
        {"candidate_id": "dual_h", "designation": "Confirm", "role_1": "보수방어형", "role_2": "추세지속형"},
        {"candidate_id": "m1", "designation": "Confirm", "role_1": "균형형"},
        {"candidate_id": "m2", "designation": "Confirm", "role_1": "균형형"},
        {"candidate_id": "e1", "designation": "Confirm", "role_1": "보수방어형"},
    ]
    result = evaluate_combo(metadata, {"main": 0, "dual_h": 1, "m1": 1, "m2": 0, "e1": 0})

    assert result.risk_off_count == 2
    assert result.hard_core_off == 1
    assert result.stage == "WEAK_CAUTION"


@pytest.mark.parametrize("i,stage_a", list(enumerate(STAGE_CODES)))
@pytest.mark.parametrize("j,stage_b", list(enumerate(STAGE_CODES)))
def test_all_sixteen_combo_merge_pairs_are_symmetric(i, stage_a, j, stage_b) -> None:
    forward = combine_combo_stages(stage_a, stage_b)
    reverse = combine_combo_stages(stage_b, stage_a)

    assert forward.stage == EXPECTED_MERGE_MATRIX[i][j]
    assert forward.stage == reverse.stage
    assert forward.label == reverse.label == STAGE_LABELS[forward.stage]
    assert forward.reason_code == reverse.reason_code


def test_role_engine_fails_closed_on_missing_ambiguous_or_nonbinary_metadata() -> None:
    base = [
        {"candidate_id": "main", "designation": "MAIN", "role_1": "균형형"},
        {"candidate_id": "c2", "designation": "Confirm", "role_1": "보수방어형"},
        {"candidate_id": "c3", "designation": "Confirm", "role_1": "공격진입형"},
        {"candidate_id": "c4", "designation": "Confirm", "role_1": "균형형"},
    ]
    states = {"main": 0, "c2": 0, "c3": 0, "c4": 0}

    missing_role = [dict(row) for row in base]
    missing_role[1].pop("role_1")
    with pytest.raises(ValueError, match="unknown authoritative role"):
        evaluate_combo(missing_role, states)

    no_main = [dict(row, designation="Confirm") for row in base]
    with pytest.raises(ValueError, match="exactly one authoritative Main"):
        evaluate_combo(no_main, states)

    multiple_mains = [dict(row) for row in base]
    multiple_mains[1]["designation"] = "MAIN"
    with pytest.raises(ValueError, match="exactly one authoritative Main"):
        evaluate_combo(multiple_mains, states)

    nonbinary = dict(states, c2=2)
    with pytest.raises(ValueError, match="binary 0/1"):
        evaluate_combo(base, nonbinary)

    with pytest.raises(ValueError, match="unsupported canonical role combination"):
        classify_role_combo("추세지속형")
    with pytest.raises(ValueError, match="duplicate role"):
        classify_role_combo("균형형", "균형형")


def test_canonical_role_order_is_deterministic() -> None:
    result = classify_role_combo("추세지속형", "균형형")
    expected = " + ".join(sorted(("추세지속형", "균형형"), key=ROLE_ORDER.index))
    assert result.canonical_combo == expected


def test_zero_early_role_combo_accepts_every_binary_input_vector() -> None:
    metadata = [
        {"candidate_id": "main", "designation": "MAIN", "role_1": "공격진입형"},
        {"candidate_id": "h_confirm", "designation": "Confirm", "role_1": "보수방어형", "role_2": "추세지속형"},
        {"candidate_id": "m1", "designation": "Confirm", "role_1": "균형형"},
        {"candidate_id": "m2", "designation": "Confirm", "role_1": "공격진입형", "role_2": "민감감지형"},
        {"candidate_id": "m3", "designation": "Confirm", "role_1": "공격진입형", "role_2": "균형형"},
    ]
    assert all(classify_role_combo(row["role_1"], row.get("role_2")).warning_class != "E" for row in metadata)

    for bitmask in range(1 << len(metadata)):
        states = {row["candidate_id"]: (bitmask >> index) & 1 for index, row in enumerate(metadata)}
        result = evaluate_combo(metadata, states)
        assert result.stage in STAGE_LABELS
        assert result.early_off == 0
        assert result.risk_off_count == sum(states.values())
