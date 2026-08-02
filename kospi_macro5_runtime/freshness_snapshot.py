from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .engine import D1C1Context, build_dependency_graph, child_combo1_specs_from_dependency_graph, read_json
from .freshness import OK_FRESHNESS_STATUSES
from .freshness_contracts import source_freshness_contracts, required_sources_for_family
from .source_consistency import blocking_source_ids


def final9_required_sources(ctx: D1C1Context) -> dict[str, list[str]]:
    final9 = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    metadata = pd.read_parquet(ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet")
    family_by_component = dict(zip(metadata["candidate_id"], metadata["indicator_id"]))
    child_specs = child_combo1_specs_from_dependency_graph(build_dependency_graph(ctx))

    out: dict[str, list[str]] = {}
    for candidate_id, spec in final9.items():
        core_components: list[str] = []
        if spec["model_type"] == "combo1":
            core_components = list(spec["component_ids"])
        else:
            for child_id in spec["component_ids"]:
                if child_id in child_specs:
                    core_components.extend(list(child_specs[child_id]["component_ids"]))
        sources: set[str] = set()
        for component_id in core_components:
            family = family_by_component.get(component_id, "")
            sources.update(required_sources_for_family(str(family)))
        out[candidate_id] = sorted(sources)
    return out


def qualify_candidates(
    snapshot: pd.DataFrame,
    source_freshness: pd.DataFrame,
    consistency: pd.DataFrame,
    required_sources: dict[str, list[str]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source_status = dict(zip(source_freshness["source_id"], source_freshness["final_freshness_status"]))
    source_actual = dict(zip(source_freshness["source_id"], source_freshness["actual_latest_available_date"]))
    source_expected = dict(zip(source_freshness["source_id"], source_freshness["expected_latest_available_date"]))
    source_lag = dict(zip(source_freshness["source_id"], source_freshness["lag_krx_sessions"]))
    blocked_sources = blocking_source_ids(consistency)
    contracts = source_freshness_contracts()
    allowed_statuses = {"FRESH"}
    conditional_statuses = {"EXPECTED_CADENCE_LAG", "NO_NEW_RELEASE_EXPECTED"}

    rows: list[dict[str, Any]] = []
    for rec in snapshot.to_dict("records"):
        candidate_id = str(rec["candidate_id"])
        required = required_sources.get(candidate_id, [])
        required_known = [sid for sid in required if sid in contracts]
        required_unknown = [sid for sid in required if sid not in contracts]
        stale = [sid for sid in required if source_status.get(sid) == "STALE"]
        errors = [sid for sid in required if source_status.get(sid) in {"FETCH_ERROR", "SCHEMA_ERROR", "INVALID_VALUE", "CONTRACT_UNBOUND"}]
        regressed = [sid for sid in required if source_status.get(sid) == "DATE_REGRESSION"]
        expected_cadence = [sid for sid in required if source_status.get(sid) in {"EXPECTED_CADENCE_LAG", "NO_NEW_RELEASE_EXPECTED"}]
        fresh = [sid for sid in required if source_status.get(sid) == "FRESH"]
        consistency_blocked = sorted(set(required).intersection(blocked_sources))
        unknown = [sid for sid in required if not source_status.get(sid) or source_status.get(sid) not in allowed_statuses | conditional_statuses | {"STALE", "FETCH_ERROR", "SCHEMA_ERROR", "INVALID_VALUE", "CONTRACT_UNBOUND", "DATE_REGRESSION"}]
        conditional_blocked = [
            sid
            for sid in expected_cadence
            if sid not in contracts or not contracts[sid].carry_forward_allowed
        ]
        empty_required = len(required) == 0
        ok = (
            not empty_required
            and not required_unknown
            and not stale
            and not errors
            and not regressed
            and not consistency_blocked
            and not unknown
            and not conditional_blocked
        )
        if ok:
            status = "FRESH" if not expected_cadence else "EXPECTED_CADENCE_LAG"
            reason = "all required sources satisfy freshness contract"
        elif consistency_blocked:
            status = "CONSISTENCY_BLOCKED"
            reason = "blocking source consistency mismatch"
        elif empty_required or required_unknown or conditional_blocked:
            status = "CONTRACT_UNBOUND"
            reason = "required source mapping missing, unknown, or conditional cadence not allowed"
        elif errors:
            status = "SOURCE_ERROR"
            reason = "one or more required sources failed"
        elif regressed:
            status = "DATE_REGRESSION"
            reason = "one or more required sources regressed"
        elif stale:
            status = "STALE"
            reason = "one or more required sources stale"
        else:
            status = "MIXED"
            reason = "mixed freshness state"

        bottleneck_candidates = sorted(
            required,
            key=lambda sid: (
                -1 if pd.isna(source_lag.get(sid)) else int(source_lag.get(sid) or 0),
                str(source_actual.get(sid) or ""),
            ),
            reverse=True,
        )
        bottleneck = bottleneck_candidates[0] if bottleneck_candidates else ""
        row = dict(rec)
        row.update(
            {
                "freshness_qualified": bool(ok),
                "shadow_actionable": bool(rec.get("calculable", False) and ok and not rec.get("official_operating_model", True)),
                "freshness_status": status,
                "freshness_reason": reason,
                "required_source_ids": "|".join(required),
                "allowed_source_ids": "|".join(fresh),
                "conditional_source_ids": "|".join(expected_cadence),
                "blocked_source_ids": "|".join(stale + errors + regressed + consistency_blocked + required_unknown + conditional_blocked),
                "unknown_status_source_ids": "|".join(unknown),
                "fresh_source_ids": "|".join(fresh),
                "expected_cadence_source_ids": "|".join(expected_cadence),
                "stale_source_ids": "|".join(stale),
                "error_source_ids": "|".join(errors + unknown),
                "regressed_source_ids": "|".join(regressed),
                "consistency_blocked_source_ids": "|".join(consistency_blocked),
                "source_bottleneck_id": bottleneck,
                "source_bottleneck_actual_date": source_actual.get(bottleneck),
                "source_bottleneck_expected_date": source_expected.get(bottleneck),
                "source_bottleneck_lag_sessions": source_lag.get(bottleneck),
                "raw_signal_changed_by_freshness": False,
            }
        )
        rows.append(row)
    out = pd.DataFrame(rows)
    summary = group_freshness_summary(out)
    return out, summary


def group_freshness_summary(snapshot: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model_type, expected in [("combo1", 4), ("combo2", 5)]:
        group = snapshot.loc[snapshot["model_type"].eq(model_type)].copy()
        calc = group["calculable"].astype(bool) if "calculable" in group else pd.Series(False, index=group.index)
        fq = group["freshness_qualified"].astype(bool) if "freshness_qualified" in group else pd.Series(False, index=group.index)
        risk = group["raw_risk_state"].fillna(0).astype(int) if "raw_risk_state" in group else pd.Series(0, index=group.index)
        out[model_type] = {
            "total_count": expected,
            "calculable_count": int(calc.sum()),
            "freshness_qualified_count": int(fq.sum()),
            "freshness_unqualified_count": int(expected - fq.sum()),
            "risk_off_calculated_count": int(risk.loc[calc].sum()),
            "risk_off_freshness_qualified_count": int(risk.loc[fq].sum()),
        }
    out["final9"] = {
        "calculated_risk_off_count": int(snapshot.loc[snapshot["calculable"].astype(bool), "raw_risk_state"].fillna(0).astype(int).sum()),
        "freshness_qualified_risk_off_count": int(snapshot.loc[snapshot["freshness_qualified"].astype(bool), "raw_risk_state"].fillna(0).astype(int).sum()),
    }
    return out
