"""Shared deterministic cases for role-stage unit and CSV QA."""

ROLE_VECTORS = [
    ("균형형", None, "M"),
    ("균형형", "추세지속형", "H"),
    ("균형형", "민감감지형", "M"),
    ("공격진입형", None, "H"),
    ("공격진입형", "추세지속형", "H"),
    ("공격진입형", "민감감지형", "M"),
    ("공격진입형", "균형형", "H"),
    ("보수방어형", None, "E"),
    ("보수방어형", "추세지속형", "H"),
    ("보수방어형", "민감감지형", "E"),
    ("보수방어형", "균형형", "M"),
]

_ROLE_FOR_CLASS = {
    "E": ("보수방어형", None),
    "M": ("균형형", None),
    "H": ("공격진입형", None),
}


def _case(name, classes, main_index, off_indices, expected_stage, expected_reason):
    metadata = []
    states = {}
    for index, warning_class in enumerate(classes):
        candidate_id = f"candidate-{index + 1}"
        role_1, role_2 = _ROLE_FOR_CLASS[warning_class]
        metadata.append({
            "candidate_id": candidate_id,
            "designation": "MAIN" if index == main_index else "Confirm",
            "role_1": role_1,
            "role_2": role_2,
        })
        states[candidate_id] = int(index in off_indices)
    return {
        "test_id": name,
        "classes": tuple(classes),
        "main_index": main_index,
        "off_indices": tuple(off_indices),
        "metadata": metadata,
        "states": states,
        "expected_stage": expected_stage,
        "expected_reason": expected_reason,
    }


COMBO_CASES = [
    _case("4_zero_off", ("E", "M", "H", "M"), 0, (), "BUY", "NO_RISK_OFF"),
    _case("4_one_early_main_on", ("M", "E", "H", "M"), 0, (1,), "BUY", "EARLY_ONLY_ONE"),
    _case("4_one_meaningful", ("M", "M", "E", "H"), 0, (1,), "WEAK_CAUTION", "ONE_MEANINGFUL_WARNING"),
    _case("4_one_core", ("M", "H", "E", "M"), 0, (1,), "WEAK_CAUTION", "ONE_CORE_WARNING"),
    _case("4_main_one_off", ("E", "M", "H", "M"), 0, (0,), "WEAK_CAUTION", "MAIN_ONE_OFF"),
    _case("4_two_early_meaningful", ("M", "E", "M", "H"), 0, (1, 2), "WEAK_CAUTION", "TWO_OFF_MAIN_ON_AT_MOST_ONE_H_CONFIRM"),
    _case("4_two_off_h_one_main_on", ("M", "E", "H", "M"), 0, (1, 2), "WEAK_CAUTION", "TWO_OFF_MAIN_ON_AT_MOST_ONE_H_CONFIRM"),
    _case("5_two_off_h_zero_main_on", ("M", "E", "M", "E", "H"), 0, (1, 2), "WEAK_CAUTION", "TWO_OFF_MAIN_ON_AT_MOST_ONE_H_CONFIRM"),
    _case("5_two_off_h_one_main_on", ("M", "E", "H", "M", "E"), 0, (1, 2), "WEAK_CAUTION", "TWO_OFF_MAIN_ON_AT_MOST_ONE_H_CONFIRM"),
    _case("5_two_off_independent_h_two_main_on", ("M", "H", "H", "M", "E"), 0, (1, 2), "STRONG_CAUTION", "TWO_OFF_AND_TWO_INDEPENDENT_H_CONFIRM"),
    _case("4_two_off_including_main", ("E", "M", "H", "M"), 0, (0, 1), "STRONG_CAUTION", "MAIN_AND_TWO_OFF"),
    _case("5_three_off_main_on", ("M", "E", "M", "H", "H"), 0, (1, 2, 3), "STRONG_CAUTION", "THREE_OR_MORE_OFF"),
    _case("4_three_of_four_main_off", ("E", "M", "H", "M"), 0, (0, 1, 2), "SELL", "MAIN_75PCT_AND_INDEPENDENT_H_CONFIRM"),
    _case("5_three_of_five_main_off", ("E", "M", "H", "E", "M"), 0, (0, 1, 2), "STRONG_CAUTION", "THREE_OR_MORE_OFF"),
    _case("5_four_off_main_on", ("M", "E", "M", "H", "H"), 0, (1, 2, 3, 4), "STRONG_CAUTION", "THREE_OR_MORE_OFF"),
    _case("5_four_off_main_off", ("E", "M", "H", "M", "H"), 0, (0, 1, 2, 3), "SELL", "MAIN_75PCT_AND_INDEPENDENT_H_CONFIRM"),
    _case("5_four_off_main_h_no_confirm_h", ("H", "M", "M", "E", "H"), 0, (0, 1, 2, 3), "STRONG_CAUTION", "BROAD_OFF_WITHOUT_INDEPENDENT_H_CONFIRM"),
    _case("5_four_off_main_h_with_confirm_h", ("H", "M", "M", "H", "E"), 0, (0, 1, 2, 3), "SELL", "MAIN_75PCT_AND_INDEPENDENT_H_CONFIRM"),
    _case("5_all_off", ("H", "M", "E", "H", "M"), 0, (0, 1, 2, 3, 4), "SELL", "ALL_RISK_OFF"),
    _case("4_all_off", ("E", "M", "H", "M"), 0, (0, 1, 2, 3), "SELL", "ALL_RISK_OFF"),
]

STAGE_CODES = ("BUY", "WEAK_CAUTION", "STRONG_CAUTION", "SELL")
EXPECTED_MERGE_MATRIX = (
    ("BUY", "WEAK_CAUTION", "WEAK_CAUTION", "STRONG_CAUTION"),
    ("WEAK_CAUTION", "WEAK_CAUTION", "STRONG_CAUTION", "SELL"),
    ("WEAK_CAUTION", "STRONG_CAUTION", "STRONG_CAUTION", "SELL"),
    ("STRONG_CAUTION", "SELL", "SELL", "SELL"),
)
