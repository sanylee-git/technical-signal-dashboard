"""Presentation-layer metadata validation and role-aware market aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from html import escape

import pandas as pd

from dashboard_role_aware_stage import (
    STAGE_LABELS,
    classify_role_combo,
    combine_combo_stages,
    evaluate_combo,
)
from dashboard_timepoints import candidate_history_rows_at_offsets


ROOT = Path(__file__).resolve().parent
DEFAULT_METADATA_PATH = ROOT / "dashboard_role_metadata.json"
TIMEPOINTS = (
    (21, "21TD", "1개월 전"),
    (10, "10TD", "2주 전"),
    (5, "5TD", "1주 전"),
    (0, "TODAY", "오늘"),
)
COMBINATION_ORDER = ("COMBO1", "COMBO2", "OVERALL")
COMBINATION_LABELS = {"COMBO1": "Combo1", "COMBO2": "Combo2", "OVERALL": "전체"}
STAGE_COLORS = {
    "BUY": "#3B82F6",
    "WEAK_CAUTION": "#22C55E",
    "STRONG_CAUTION": "#F97316",
    "SELL": "#EF4444",
    "UNAVAILABLE": "#FF8C69",
}


class MetadataValidationError(ValueError):
    """Raised when explicit role metadata no longer matches an operating Final set."""


def load_role_metadata(path: str | Path = DEFAULT_METADATA_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema_version") != 1 or data.get("authority") != "user_explicitly_confirmed":
        raise MetadataValidationError("unsupported or unauthoritative role metadata document")
    return data


def role_warning_classes(
    market: str,
    metadata_document: Mapping[str, Any] | None = None,
    *,
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
) -> dict[str, str]:
    """Map locked candidate IDs to their existing E/M/H role classification."""
    document = load_role_metadata(metadata_path) if metadata_document is None else metadata_document
    market_metadata = document.get("markets", {}).get(market, {})
    classes: dict[str, str] = {}
    for family in ("COMBO1", "COMBO2"):
        for record in market_metadata.get(family, []):
            candidate_id = str(record.get("candidate_id", "")).strip()
            if not candidate_id or candidate_id in classes:
                raise MetadataValidationError(f"candidate role metadata is missing or duplicated: {candidate_id}")
            derived = classify_role_combo(record.get("role_1"), record.get("role_2")).warning_class
            declared = str(record.get("confirmation_type", "")).strip().upper()
            if declared and declared != derived:
                raise MetadataValidationError(f"confirmation type conflicts with role metadata: {candidate_id}")
            classes[candidate_id] = declared or derived
    if not classes:
        raise MetadataValidationError(f"no candidate role metadata for {market}")
    return classes


def order_candidates_main_emh(
    candidate_ids: Sequence[object],
    main_ids: Sequence[object],
    warning_classes: Mapping[str, str],
) -> list[str]:
    """Place Main first, then Confirm candidates by E, M, H; preserve ties."""
    main = {str(candidate_id) for candidate_id in main_ids}
    class_order = {"E": 0, "M": 1, "H": 2}
    ids = [str(candidate_id) for candidate_id in candidate_ids]
    return sorted(
        ids,
        key=lambda candidate_id: (
            0 if candidate_id in main else 1,
            class_order.get(str(warning_classes.get(candidate_id, "")).upper(), 3),
        ),
    )


def _family_column(final: pd.DataFrame) -> str:
    for column in ("model_family", "family"):
        if column in final.columns:
            return column
    raise MetadataValidationError("operational Final has no family column")


def validate_market_metadata(
    market: str,
    final: pd.DataFrame,
    metadata_document: Mapping[str, Any] | None = None,
    *,
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
) -> list[dict[str, Any]]:
    document = load_role_metadata(metadata_path) if metadata_document is None else metadata_document
    markets = document.get("markets", {})
    market_metadata = markets.get(market)
    if not isinstance(market_metadata, Mapping):
        raise MetadataValidationError(f"no authoritative metadata for {market}")
    if "candidate_id" not in final.columns:
        raise MetadataValidationError("operational Final has no candidate_id column")

    family_col = _family_column(final)
    actual_ids: dict[str, list[str]] = {}
    for family in ("COMBO1", "COMBO2"):
        actual_ids[family] = (
            final.loc[final[family_col].astype(str).str.upper().eq(family), "candidate_id"]
            .astype(str)
            .tolist()
        )
    operational_ids_all = final["candidate_id"].astype(str).tolist()
    operational_families = final[family_col].astype(str).str.upper()
    unexpected_family_count = int((~operational_families.isin(("COMBO1", "COMBO2"))).sum())
    metadata_ids_all = [
        str(item.get("candidate_id", "")).strip()
        for family in ("COMBO1", "COMBO2")
        for item in market_metadata.get(family, [])
        if isinstance(item, Mapping)
    ]
    global_exact_match = (
        len(operational_ids_all) == 10
        and len(set(operational_ids_all)) == 10
        and len(metadata_ids_all) == 10
        and set(operational_ids_all) == set(metadata_ids_all)
        and unexpected_family_count == 0
    )

    result: list[dict[str, Any]] = []
    all_metadata_ids: list[str] = []
    for family in ("COMBO1", "COMBO2"):
        records = market_metadata.get(family, [])
        if not isinstance(records, list):
            records = []
        metadata_ids = [str(row.get("candidate_id", "")).strip() for row in records]
        all_metadata_ids.extend(metadata_ids)
        duplicate_ids = sorted({candidate_id for candidate_id in metadata_ids if metadata_ids.count(candidate_id) > 1})
        operational_ids = actual_ids[family]
        missing_ids = sorted(set(operational_ids) - set(metadata_ids))
        extra_ids = sorted(set(metadata_ids) - set(operational_ids))
        main_count = sum(str(row.get("designation", "")).strip().upper() == "MAIN" for row in records)
        confirm_count = sum(str(row.get("designation", "")).strip().upper() == "CONFIRM" for row in records)
        role_1_missing = sum(not str(row.get("role_1", "")).strip() for row in records)
        invalid_roles = 0
        for row in records:
            try:
                classify_role_combo(row.get("role_1"), row.get("role_2"))
            except (TypeError, ValueError):
                invalid_roles += 1
        exact_match = (
            len(operational_ids) == 5
            and len(set(operational_ids)) == 5
            and len(metadata_ids) == 5
            and set(operational_ids) == set(metadata_ids)
        )
        passed = (
            exact_match
            and global_exact_match
            and not duplicate_ids
            and not missing_ids
            and not extra_ids
            and main_count == 1
            and confirm_count == 4
            and role_1_missing == 0
            and invalid_roles == 0
        )
        result.append({
            "market": market,
            "combo": family,
            "expected_candidates": 5,
            "operational_candidates": len(operational_ids),
            "metadata_candidates": len(metadata_ids),
            "operational_candidate_total": len(operational_ids_all),
            "unexpected_family_count": unexpected_family_count,
            "market_candidate_id_exact_match": int(global_exact_match),
            "candidate_id_exact_match": int(exact_match),
            "missing_candidate_ids": "|".join(missing_ids),
            "extra_candidate_ids": "|".join(extra_ids),
            "duplicate_candidate_ids": "|".join(duplicate_ids),
            "main_count": main_count,
            "confirm_count": confirm_count,
            "role_1_missing_count": role_1_missing,
            "invalid_role_combo_count": invalid_roles,
            "status": "PASS" if passed else "FAIL",
        })

    cross_combo_duplicates = sorted({candidate_id for candidate_id in all_metadata_ids if all_metadata_ids.count(candidate_id) > 1})
    if cross_combo_duplicates:
        for row in result:
            row["duplicate_candidate_ids"] = "|".join(sorted(set(row["duplicate_candidate_ids"].split("|")) - {""} | set(cross_combo_duplicates)))
            row["status"] = "FAIL"
    return result


def _snapshot_index(snapshot: pd.DataFrame) -> tuple[dict[str, pd.Series], set[str]]:
    if not isinstance(snapshot, pd.DataFrame) or "candidate_id" not in snapshot.columns:
        return {}, set()
    ids = snapshot["candidate_id"].astype(str)
    duplicate_ids = set(ids[ids.duplicated(keep=False)].tolist())
    indexed = {
        str(row["candidate_id"]): row
        for row in snapshot.to_dict("records")
        if str(row.get("candidate_id", "")) not in duplicate_ids
    }
    return indexed, duplicate_ids


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _binary_state(value: object) -> int | None:
    if _is_missing(value):
        return None
    if isinstance(value, str) and value.strip() not in {"0", "1"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number not in (0.0, 1.0):
        return None
    return int(number)


def _candidate_state(
    candidate_id: str,
    offset: int,
    snapshot_by_id: Mapping[str, pd.Series | Mapping[str, Any]],
    duplicate_snapshot_ids: set[str],
    history: pd.DataFrame | None,
) -> tuple[int | None, str, str]:
    if candidate_id in duplicate_snapshot_ids:
        return None, "", f"DUPLICATE_SNAPSHOT_ROW:{candidate_id}"
    row = snapshot_by_id.get(candidate_id)
    if row is None:
        return None, "", f"SNAPSHOT_ROW_MISSING:{candidate_id}"
    if offset in (21, 10):
        basis = row.get("basis_date")
        selected = candidate_history_rows_at_offsets(
            history,
            candidate_id,
            basis,
            offsets=(offset,),
            valid_col="valid_signal",
        )[offset]
        if selected is None:
            return None, "", f"HISTORY_OFFSET_MISSING:{candidate_id}:{offset}TD"
        state = selected.get("raw_risk_state")
        date = selected.get("date")
    elif offset == 5:
        status = str(row.get("status", "USABLE"))
        availability = str(row.get("availability_status", ""))
        if status != "USABLE" or availability == "PROVISIONAL_UNAVAILABLE":
            return None, "", f"CANDIDATE_NOT_USABLE:{candidate_id}"
        state = row.get("week_ago_raw_risk_state")
        date = row.get("week_ago_basis_date")
    elif offset == 0:
        status = str(row.get("status", "USABLE"))
        availability = str(row.get("availability_status", ""))
        if status != "USABLE" or availability == "PROVISIONAL_UNAVAILABLE":
            return None, "", f"CANDIDATE_NOT_USABLE:{candidate_id}"
        state = row.get("raw_risk_state")
        date = row.get("basis_date")
    else:
        return None, "", f"UNSUPPORTED_TIMEPOINT_OFFSET:{offset}"

    parsed_state = _binary_state(state)
    if parsed_state is None:
        return None, "", f"INVALID_OR_MISSING_RISK_STATE:{candidate_id}:{offset}TD"
    date_text = "" if _is_missing(date) else pd.Timestamp(date).strftime("%Y-%m-%d")
    return parsed_state, date_text, ""


def _unavailable_row(
    market: str,
    timepoint_code: str,
    timepoint: str,
    offset: int,
    combination: str,
    reason: str,
    *,
    legacy_stage: str = "",
) -> dict[str, Any]:
    return {
        "market": market,
        "timepoint_code": timepoint_code,
        "timepoint": timepoint,
        "offset_trading_days": offset,
        "combination": combination,
        "evaluation_dates": "",
        "model_count": "",
        "risk_off_count": "",
        "main_off": "",
        "E_off": "",
        "M_off": "",
        "H_off": "",
        "stage_code": "UNAVAILABLE",
        "stage_label": "계산 불가",
        "risk_side": "",
        "reason_code": "UNAVAILABLE",
        "metadata_status": "FAIL" if reason.startswith("METADATA_") else "PASS",
        "state_status": "UNAVAILABLE",
        "unavailable_reason": reason,
        "legacy_market_stage": legacy_stage,
    }


def compute_role_aware_market_outputs(
    market: str,
    final: pd.DataFrame,
    snapshot: pd.DataFrame,
    history: pd.DataFrame | None,
    *,
    metadata_document: Mapping[str, Any] | None = None,
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
    legacy_stages: Mapping[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    document = load_role_metadata(metadata_path) if metadata_document is None else metadata_document
    try:
        validation = validate_market_metadata(market, final, document)
    except MetadataValidationError as exc:
        validation = []
        metadata_error = str(exc)
    else:
        metadata_error = ""
    metadata_ready = len(validation) == 2 and all(row["status"] == "PASS" for row in validation)
    metadata = document.get("markets", {}).get(market, {})
    snapshot_by_id, duplicate_snapshot_ids = _snapshot_index(snapshot)
    result: list[dict[str, Any]] = []
    for offset, code, label in TIMEPOINTS:
        combo_decisions: dict[str, Any] = {}
        for family in ("COMBO1", "COMBO2"):
            legacy = (legacy_stages or {}).get((family, code), "")
            if not metadata_ready:
                detail = metadata_error or "operational candidate IDs do not exactly match explicit role metadata"
                result.append(_unavailable_row(market, code, label, offset, family, f"METADATA_VALIDATION_FAILED:{detail}", legacy_stage=legacy))
                combo_decisions[family] = None
                continue
            candidate_records = metadata[family]
            states: dict[str, int] = {}
            dates: set[str] = set()
            state_errors: list[str] = []
            for record in candidate_records:
                candidate_id = str(record["candidate_id"])
                state, evaluation_date, error = _candidate_state(
                    candidate_id, offset, snapshot_by_id, duplicate_snapshot_ids, history
                )
                if error:
                    state_errors.append(error)
                else:
                    states[candidate_id] = int(state)
                    if evaluation_date:
                        dates.add(evaluation_date)
            if state_errors:
                decision = None
                result.append(_unavailable_row(
                    market,
                    code,
                    label,
                    offset,
                    family,
                    "|".join(state_errors),
                    legacy_stage=legacy,
                ))
            else:
                decision = evaluate_combo(candidate_records, states)
                result.append({
                    "market": market,
                    "timepoint_code": code,
                    "timepoint": label,
                    "offset_trading_days": offset,
                    "combination": family,
                    "evaluation_dates": "|".join(sorted(dates)),
                    "model_count": decision.model_count,
                    "risk_off_count": decision.risk_off_count,
                    "main_off": int(bool(decision.main_off)),
                    "E_off": decision.early_off,
                    "M_off": decision.meaningful_off,
                    "H_off": decision.hard_core_off,
                    "stage_code": decision.stage,
                    "stage_label": decision.label,
                    "risk_side": "Risk-off" if decision.stage == "SELL" else "Risk-on",
                    "reason_code": decision.reason_code,
                    "metadata_status": "PASS",
                    "state_status": "PASS",
                    "unavailable_reason": "",
                    "legacy_market_stage": legacy,
                })
            combo_decisions[family] = decision

        legacy_overall = (legacy_stages or {}).get(("OVERALL", code), "")
        first, second = combo_decisions.get("COMBO1"), combo_decisions.get("COMBO2")
        if first is None or second is None:
            reasons = [
                row["unavailable_reason"]
                for row in result[-2:]
                if row["combination"] in {"COMBO1", "COMBO2"}
            ]
            result.append(_unavailable_row(
                market, code, label, offset, "OVERALL", "|".join(reasons) or "COMBO_INPUT_UNAVAILABLE",
                legacy_stage=legacy_overall,
            ))
        else:
            merged = combine_combo_stages(first.stage, second.stage)
            combo_rows = result[-2:]
            evaluation_dates = sorted({date for row in combo_rows for date in str(row["evaluation_dates"]).split("|") if date})
            result.append({
                "market": market,
                "timepoint_code": code,
                "timepoint": label,
                "offset_trading_days": offset,
                "combination": "OVERALL",
                "evaluation_dates": "|".join(evaluation_dates),
                "model_count": "",
                "risk_off_count": "",
                "main_off": "",
                "E_off": "",
                "M_off": "",
                "H_off": "",
                "stage_code": merged.stage,
                "stage_label": merged.label,
                "risk_side": "Risk-off" if merged.stage == "SELL" else "Risk-on",
                "reason_code": merged.reason_code,
                "metadata_status": "PASS",
                "state_status": "PASS",
                "unavailable_reason": "",
                "legacy_market_stage": legacy_overall,
            })
    return result


def format_role_stage_sequence(outputs: list[Mapping[str, Any]], combination: str) -> str:
    by_code = {
        str(row.get("timepoint_code")): row
        for row in outputs
        if row.get("combination") == combination
    }
    parts: list[str] = []
    for _offset, code, _label in TIMEPOINTS:
        row = by_code.get(code, {})
        stage_code = str(row.get("stage_code", "UNAVAILABLE"))
        label = str(row.get("stage_label", "계산 불가"))
        color = STAGE_COLORS.get(stage_code, STAGE_COLORS["UNAVAILABLE"])
        parts.append(f"<span style='color:{color};font-weight:700'>{escape(label)}</span>")
    arrow = "<span style='color:rgba(255,255,255,.36);padding:0 4px'>→</span>"
    return arrow.join(parts)
