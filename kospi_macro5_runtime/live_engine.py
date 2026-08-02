from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .core15 import compute_core15_component
from .engine import D1C1Context, build_dependency_graph, child_combo1_specs_from_dependency_graph, read_json
from .validity import hysteresis_from_nullable_counts, t1_position_from_nullable_raw


def combo_from_components_nullable(source: pd.DataFrame, component_ids: list[str], k: int, l: int) -> pd.DataFrame:
    missing = [cid for cid in component_ids if cid not in source.columns]
    if missing:
        out = pd.DataFrame({"date": source["date"]})
        out["active_count"] = pd.NA
        out["raw_risk_state"] = pd.NA
        out["risk_start_signal"] = 0
        out["risk_end_signal"] = 0
        out["valid_signal"] = False
        out["calculation_status"] = "MISSING_REQUIRED_INPUT"
        out["calculation_reason"] = "|".join(missing[:10])
        return out
    work = source[["date", *component_ids]].copy()
    valid = work[component_ids].notna().all(axis=1)
    active = work[component_ids].where(valid, pd.NA).sum(axis=1, min_count=len(component_ids))
    h = hysteresis_from_nullable_counts(active, valid, int(k), int(l), component_count=len(component_ids))
    out = pd.DataFrame({"date": work["date"], "active_count": active.astype("Int16")})
    out = pd.concat([out, h], axis=1)
    out["calculation_status"] = out["valid_signal"].map(lambda ok: "CALCULABLE" if ok else "MISSING_REQUIRED_INPUT")
    out["calculation_reason"] = out["valid_signal"].map(lambda ok: "" if ok else "one or more components invalid")
    return out


def compute_live_core15(frame: pd.DataFrame, metadata: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    for _, row in metadata.iterrows():
        cid = str(row["candidate_id"])
        try:
            result = compute_core15_component(frame, row).frame
            result["component_id"] = cid
            result["calculation_status"] = "CALCULABLE"
            result["calculation_reason"] = ""
            frames.append(result)
            rows.append({"component_id": cid, "indicator_id": row["indicator_id"], "calculation_status": "CALCULABLE", "calculation_reason": ""})
        except Exception as exc:
            rows.append({"component_id": cid, "indicator_id": row.get("indicator_id", ""), "calculation_status": "SOURCE_ERROR", "calculation_reason": repr(exc)})
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), pd.DataFrame(rows)


def compute_live_tree(ctx: D1C1Context, transformed: pd.DataFrame) -> dict[str, pd.DataFrame]:
    graph = build_dependency_graph(ctx)
    metadata = pd.read_parquet(ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet")
    metadata = metadata[metadata["candidate_id"].isin(graph["required_core15_components"])].copy()
    core, core_status = compute_live_core15(transformed, metadata)
    core_wide = core.pivot(index="date", columns="component_id", values="risk_state").reset_index()

    final9 = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    child_specs = child_combo1_specs_from_dependency_graph(graph)

    child_rows: list[pd.DataFrame] = []
    for child_id in graph["required_child_combo1"]:
        row = child_specs[child_id]
        component_ids = list(row["component_ids"])
        replay = combo_from_components_nullable(core_wide, component_ids, int(row["K"]), int(row["L"]))
        replay["combo1_id"] = child_id
        replay["component_count"] = len(component_ids)
        child_rows.append(replay)
    child = pd.concat(child_rows, ignore_index=True) if child_rows else pd.DataFrame()
    child_wide = child.pivot(index="date", columns="combo1_id", values="raw_risk_state").reset_index()

    final_rows: list[pd.DataFrame] = []
    for candidate_id, spec in final9.items():
        source = core_wide if spec["model_type"] == "combo1" else child_wide
        replay = combo_from_components_nullable(source, list(spec["component_ids"]), int(spec["K"]), int(spec["L"]))
        t1 = t1_position_from_nullable_raw(replay["raw_risk_state"], replay["valid_signal"])
        replay = pd.concat([replay, t1], axis=1)
        replay["candidate_id"] = candidate_id
        replay["model_type"] = spec["model_type"]
        replay["component_count"] = len(spec["component_ids"])
        replay["K"] = int(spec["K"])
        replay["L"] = int(spec["L"])
        replay["component_ids_json"] = json.dumps(spec["component_ids"], ensure_ascii=False)
        final_rows.append(replay)
    final = pd.concat(final_rows, ignore_index=True) if final_rows else pd.DataFrame()
    return {"core15": core, "core15_status": core_status, "child_combo1": child, "final9": final}
