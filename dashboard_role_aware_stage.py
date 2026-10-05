"""Deterministic presentation-only role-aware market-stage engine.

The engine accepts already-computed candidate states and explicit authoritative
metadata. It does not select candidates or calculate model/risk states.

E/M/H classify the character/depth of each candidate's warning; they are not
an ordered state machine. Risk-off count measures breadth, while Main confirms
the transition. A broad Main-confirmed Red decision additionally requires an
independent Risk-off Confirm candidate classified H, unless every model is off.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Mapping, Sequence


ROLE_ORDER = (
    "균형형",
    "공격진입형",
    "보수방어형",
    "추세지속형",
    "민감감지형",
)

_ROLE_SEVERITY_BY_SET = {
    frozenset(("균형형",)): "M",
    frozenset(("균형형", "추세지속형")): "H",
    frozenset(("균형형", "민감감지형")): "M",
    frozenset(("공격진입형",)): "H",
    frozenset(("공격진입형", "추세지속형")): "H",
    frozenset(("공격진입형", "민감감지형")): "M",
    frozenset(("공격진입형", "균형형")): "H",
    frozenset(("보수방어형",)): "E",
    frozenset(("보수방어형", "추세지속형")): "H",
    frozenset(("보수방어형", "민감감지형")): "E",
    frozenset(("보수방어형", "균형형")): "M",
}

STAGE_LABELS = {
    "BUY": "🟢 매수 (Risk-on)",
    "WEAK_CAUTION": "🟡 약한경계 (Risk-on)",
    "STRONG_CAUTION": "🟠 강한경계 (Risk-on)",
    "SELL": "🔴 매도 (Risk-off)",
}
STAGE_ORDER = ("BUY", "WEAK_CAUTION", "STRONG_CAUTION", "SELL")

_MERGE_RESULTS = {
    ("BUY", "BUY"): "BUY",
    ("BUY", "WEAK_CAUTION"): "WEAK_CAUTION",
    ("BUY", "STRONG_CAUTION"): "WEAK_CAUTION",
    ("BUY", "SELL"): "STRONG_CAUTION",
    ("WEAK_CAUTION", "WEAK_CAUTION"): "WEAK_CAUTION",
    ("WEAK_CAUTION", "STRONG_CAUTION"): "STRONG_CAUTION",
    ("WEAK_CAUTION", "SELL"): "SELL",
    ("STRONG_CAUTION", "STRONG_CAUTION"): "STRONG_CAUTION",
    ("STRONG_CAUTION", "SELL"): "SELL",
    ("SELL", "SELL"): "SELL",
}


@dataclass(frozen=True)
class RoleClassification:
    canonical_combo: str
    warning_class: str


@dataclass(frozen=True)
class StageDecision:
    stage: str
    label: str
    reason_code: str
    model_count: int | None = None
    risk_off_count: int | None = None
    main_off: bool | None = None
    early_off: int | None = None
    meaningful_off: int | None = None
    hard_core_off: int | None = None


def classify_role_combo(role_1: object, role_2: object = None) -> RoleClassification:
    """Canonicalize an explicitly assigned role pair and classify it E/M/H."""
    roles = [_normalize_role(role_1)]
    if role_2 is not None and str(role_2).strip():
        roles.append(_normalize_role(role_2))
    if len(roles) != len(set(roles)):
        raise ValueError("duplicate role in role pair")
    if len(roles) > 2:
        raise ValueError("a candidate may have at most two roles")

    role_set = frozenset(roles)
    warning_class = _ROLE_SEVERITY_BY_SET.get(role_set)
    if warning_class is None:
        raise ValueError(f"unsupported canonical role combination: {sorted(role_set)}")
    ordered = sorted(role_set, key=ROLE_ORDER.index)
    return RoleClassification(" + ".join(ordered), warning_class)


def evaluate_combo(
    candidate_metadata: Sequence[Mapping[str, object]],
    risk_state_by_candidate: Mapping[str, object],
) -> StageDecision:
    """Evaluate one Combo from explicit roles, designation, and binary states."""
    if not candidate_metadata:
        raise ValueError("candidate metadata is empty")

    candidate_ids: set[str] = set()
    main_ids: list[str] = []
    severity_by_id: dict[str, str] = {}
    state_by_id: dict[str, int] = {}

    for metadata in candidate_metadata:
        raw_candidate_id = metadata.get("candidate_id")
        candidate_id = "" if raw_candidate_id is None else str(raw_candidate_id).strip()
        if not candidate_id or candidate_id in candidate_ids:
            raise ValueError("candidate_id must be present and unique within a Combo")
        candidate_ids.add(candidate_id)

        designation = _normalize_designation(metadata.get("designation"))
        if designation == "MAIN":
            main_ids.append(candidate_id)
        severity_by_id[candidate_id] = classify_role_combo(
            metadata.get("role_1"), metadata.get("role_2")
        ).warning_class
        if candidate_id not in risk_state_by_candidate:
            raise ValueError(f"authoritative risk state missing for {candidate_id}")
        state_by_id[candidate_id] = _normalize_binary_state(risk_state_by_candidate[candidate_id])

    if len(main_ids) != 1:
        raise ValueError(f"exactly one authoritative Main is required; found {len(main_ids)}")
    if set(risk_state_by_candidate) != candidate_ids:
        raise ValueError("risk-state candidates do not match metadata candidates")

    main_off = state_by_id[main_ids[0]] == 1
    main_id = main_ids[0]
    off_by_class = {key: 0 for key in ("E", "M", "H")}
    for candidate_id, state in state_by_id.items():
        if state == 1:
            # One candidate contributes exactly one vote, even with two roles.
            off_by_class[severity_by_id[candidate_id]] += 1

    risk_off_count = sum(off_by_class.values())
    hard_core_confirm_off = sum(
        state == 1
        and candidate_id != main_id
        and severity_by_id[candidate_id] == "H"
        for candidate_id, state in state_by_id.items()
    )
    count = len(candidate_ids)
    stage, reason = _combo_rule(
        model_count=count,
        risk_off_count=risk_off_count,
        main_off=main_off,
        early_off=off_by_class["E"],
        meaningful_off=off_by_class["M"],
        hard_core_off=off_by_class["H"],
        hard_core_confirm_off=hard_core_confirm_off,
    )
    return StageDecision(
        stage=stage,
        label=STAGE_LABELS[stage],
        reason_code=reason,
        model_count=count,
        risk_off_count=risk_off_count,
        main_off=main_off,
        early_off=off_by_class["E"],
        meaningful_off=off_by_class["M"],
        hard_core_off=off_by_class["H"],
    )


def combine_combo_stages(combo1_stage: str, combo2_stage: str) -> StageDecision:
    """Apply the symmetric Combo1/Combo2 merge table."""
    if combo1_stage not in STAGE_LABELS or combo2_stage not in STAGE_LABELS:
        raise ValueError("unknown Combo stage")
    pair = tuple(sorted((combo1_stage, combo2_stage), key=STAGE_ORDER.index))
    stage = _MERGE_RESULTS[pair]
    reason = f"MERGE_{pair[0]}_AND_{pair[1]}"
    return StageDecision(stage=stage, label=STAGE_LABELS[stage], reason_code=reason)


def _combo_rule(
    *,
    model_count: int,
    risk_off_count: int,
    main_off: bool,
    early_off: int,
    meaningful_off: int,
    hard_core_off: int,
    hard_core_confirm_off: int,
) -> tuple[str, str]:
    if early_off + meaningful_off + hard_core_off != risk_off_count:
        raise ValueError("E_off + M_off + H_off must equal R")

    if risk_off_count == model_count:
        return "SELL", "ALL_RISK_OFF"
    if main_off and risk_off_count * 4 >= model_count * 3:
        if hard_core_confirm_off >= 1:
            return "SELL", "MAIN_75PCT_AND_INDEPENDENT_H_CONFIRM"
        return "STRONG_CAUTION", "BROAD_OFF_WITHOUT_INDEPENDENT_H_CONFIRM"

    if risk_off_count >= 3:
        return "STRONG_CAUTION", "THREE_OR_MORE_OFF"
    if risk_off_count == 2:
        if main_off:
            return "STRONG_CAUTION", "MAIN_AND_TWO_OFF"
        if hard_core_confirm_off >= 2:
            return "STRONG_CAUTION", "TWO_OFF_AND_TWO_INDEPENDENT_H_CONFIRM"
        return "WEAK_CAUTION", "TWO_OFF_MAIN_ON_AT_MOST_ONE_H_CONFIRM"
    if risk_off_count == 1:
        if early_off == 1 and not main_off:
            return "BUY", "EARLY_ONLY_ONE"
        if main_off:
            return "WEAK_CAUTION", "MAIN_ONE_OFF"
        if meaningful_off:
            return "WEAK_CAUTION", "ONE_MEANINGFUL_WARNING"
        return "WEAK_CAUTION", "ONE_CORE_WARNING"
    return "BUY", "NO_RISK_OFF"


def _normalize_role(value: object) -> str:
    role = "" if value is None else str(value).strip()
    if role not in ROLE_ORDER:
        raise ValueError(f"unknown authoritative role: {role!r}")
    return role


def _normalize_designation(value: object) -> str:
    designation = "" if value is None else str(value).strip().upper()
    if designation in {"MAIN", "MAIN1"}:
        return "MAIN"
    if designation == "CONFIRM":
        return "CONFIRM"
    raise ValueError(f"unknown authoritative designation: {value!r}")


def _normalize_binary_state(value: object) -> int:
    if isinstance(value, str) and value.strip() not in {"0", "1"}:
        raise ValueError(f"risk state must be binary 0/1, got {value!r}")
    if not isinstance(value, (str, Real)):
        raise ValueError(f"risk state must be binary 0/1, got {value!r}")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"risk state must be binary 0/1, got {value!r}") from exc
    if not math.isfinite(numeric) or numeric not in (0.0, 1.0):
        raise ValueError(f"risk state must be binary 0/1, got {value!r}")
    return int(numeric)
