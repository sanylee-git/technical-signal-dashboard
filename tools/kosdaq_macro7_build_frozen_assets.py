#!/usr/bin/env python3
"""Build immutable Macro7 Frozen assets from D0/D0.1-pinned research inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "kosdaq_macro7_assets"
REPORTS = ROOT / "reports"
D01 = REPORTS / "kosdaq_macro7_d0_1_stage2_provenance.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(frame: pd.DataFrame, sort_keys: list[str]) -> str:
    stable = frame.copy().sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
    for column in stable.columns:
        if pd.api.types.is_datetime64_any_dtype(stable[column]):
            stable[column] = stable[column].dt.strftime("%Y-%m-%d")
    payload = stable.to_csv(index=False, na_rep="<NA>", float_format="%.17g", lineterminator="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hysteresis(active: np.ndarray, k: int, l: int) -> np.ndarray:
    result = np.zeros(len(active), dtype=bool)
    state = False
    for index, count in enumerate(active):
        state = True if count >= k else False if count <= l else state
        result[index] = state
    return result


def combine(core: pd.DataFrame, combo_id: str, ids: list[str], k: int, l: int, evaluation_start: str) -> pd.DataFrame:
    selected = core.loc[(core.candidate_id.isin(ids)) & (core.date.ge(pd.Timestamp(evaluation_start)))]
    state = selected.pivot(index="date", columns="candidate_id", values="risk_state").reindex(columns=ids).astype(bool)
    valid = selected.pivot(index="date", columns="candidate_id", values="valid_signal").reindex(columns=ids).astype(bool)
    composite_valid = valid.all(axis=1)
    invalid_component_days = int((~composite_valid).sum())
    if invalid_component_days:
        raise ValueError(f"INVALID_NOT_RISK_ON: {combo_id} has {invalid_component_days} invalid evaluation dates")
    active = state.sum(axis=1).to_numpy(dtype=np.uint8)
    raw = hysteresis(active, k, l)
    prior = np.r_[False, raw[:-1]]
    return pd.DataFrame({"combo_id": combo_id, "date": state.index, "active_count": active, "raw_risk_state": raw, "valid": composite_valid.to_numpy(bool), "risk_start": raw & ~prior, "risk_end": ~raw & prior})


def final_t1(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    raw = out.raw_risk_state.to_numpy(bool)
    out["risk_off_t1"] = np.r_[False, raw[:-1]]
    out["invest_position"] = (~out.risk_off_t1).astype(np.int8)
    return out


def asset_entry(role: str, path: Path, frame: pd.DataFrame | None, sort_keys: list[str], usage: str, provenance: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "logical_role": role,
        "relative_path": str(path.relative_to(ASSETS)),
        "file_sha256": sha256(path),
        "usage": usage,
        "source_provenance": provenance,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if frame is not None:
        entry.update({"semantic_sha256": semantic_hash(frame, sort_keys), "schema": {column: str(dtype) for column, dtype in frame.dtypes.items()}, "row_count": len(frame), "first_date": str(pd.to_datetime(frame.date).min().date()) if "date" in frame else None, "last_date": str(pd.to_datetime(frame.date).max().date()) if "date" in frame else None})
    return entry


def main() -> None:
    d01 = json.loads(D01.read_text(encoding="utf-8"))
    if d01["gate"] != "PASS_KOSDAQ_MACRO7_D0_1_STAGE2_PROVENANCE_READY":
        raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_D01_PROVENANCE_DRIFT")
    for rel, expected in d01["d0_contract_files_sha256"].items():
        if sha256(ROOT / rel) != expected:
            raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_D0_CONTRACT_DRIFT")
    for source in d01["research_sources"].values():
        if sha256(Path(source["path"])) != source["sha256"]:
            raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_RESEARCH_SOURCE_DRIFT")
    for matrix in d01["required_matrix_files"]:
        if sha256(Path(matrix["absolute_source_path"])) != matrix["sha256"]:
            raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_RESEARCH_SOURCE_DRIFT")

    frozen_dir = ASSETS / "frozen"
    if frozen_dir.exists():
        raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_FROZEN_ASSET_ALREADY_EXISTS")
    frozen_dir.mkdir(parents=True)
    final = pd.read_csv(ASSETS / "kosdaq_macro7_final10.csv")
    evaluation_start = str(final.evaluation_start.iloc[0])
    child_map = pd.read_csv(ASSETS / "kosdaq_macro7_combo2_child_mapping.csv")
    metadata_path = Path(d01["research_sources"]["candidate_metadata"]["path"])
    metadata = pd.read_parquet(metadata_path)
    required_ids = set()
    for value in final.loc[final.model_family.eq("COMBO1"), "candidate_ids"].dropna():
        required_ids.update(str(value).split("|"))
    for value in child_map.child_candidate_ids.dropna():
        required_ids.update(str(value).split("|"))
    definitions = metadata.loc[metadata.candidate_id.isin(required_ids)].copy().sort_values("candidate_id", kind="mergesort")
    if len(definitions) != len(required_ids):
        raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_SIGNAL_DEFINITION_UNRESOLVED")
    definition_path = ASSETS / "kosdaq_macro7_signal_definitions.csv"
    definitions.to_csv(definition_path, index=False, lineterminator="\n")

    source_frozen = Path(d01["research_sources"]["frozen_parquet"]["path"])
    frozen_path = frozen_dir / "frozen_kosdaq_macro_snapshot.parquet"
    shutil.copyfile(source_frozen, frozen_path)
    if sha256(frozen_path) != d01["research_sources"]["frozen_parquet"]["sha256"]:
        raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D1_FROZEN_COPY_SHA")

    series_by_id = {str(row.candidate_id): str(row.source_series_id if pd.notna(row.source_series_id) else row.indicator_id) for row in definitions.itertuples(index=False)}
    matrix_lookup = {item["logical_role"]: Path(item["absolute_source_path"]) for item in d01["required_matrix_files"]}
    calendar: pd.Series | None = None
    core_parts = []
    for series_id in sorted(set(series_by_id.values())):
        names = {suffix: matrix_lookup[f"{series_id}_{suffix}"] for suffix in ["risk_state", "risk_start", "risk_end", "valid_signal"]}
        frames = {name: pd.read_parquet(path).set_index("date") for name, path in names.items()}
        dates = pd.to_datetime(frames["risk_state"].index).normalize()
        if calendar is None:
            calendar = pd.Series(dates, name="date")
        ids = [candidate_id for candidate_id, source_id in series_by_id.items() if source_id == series_id]
        for candidate_id in ids:
            core_parts.append(pd.DataFrame({
                "candidate_id": candidate_id,
                "date": dates,
                "risk_state": frames["risk_state"][candidate_id].to_numpy(bool),
                "risk_start": frames["risk_start"][candidate_id].to_numpy(bool),
                "risk_end": frames["risk_end"][candidate_id].to_numpy(bool),
                "valid_signal": frames["valid_signal"][candidate_id].to_numpy(bool),
            }))
    core = pd.concat(core_parts, ignore_index=True).sort_values(["candidate_id", "date"], kind="mergesort")
    core_path = frozen_dir / "core_signal_reference.parquet"
    core.to_parquet(core_path, index=False)

    child_parts = []
    for child_id, group in child_map.groupby("child_combo1_id", sort=True):
        row = group.iloc[0]
        child_parts.append(combine(core, child_id, str(row.child_candidate_ids).split("|"), int(row.child_K), int(row.child_L), evaluation_start))
    child = pd.concat(child_parts, ignore_index=True)
    child_path = frozen_dir / "material_child_combo1_raw_reference.parquet"
    child.to_parquet(child_path, index=False)

    final1_parts = []
    for row in final.loc[final.model_family.eq("COMBO1")].itertuples(index=False):
        final1_parts.append(combine(core, row.candidate_id, str(row.candidate_ids).split("|"), int(row.K), int(row.L), evaluation_start))
    final1 = pd.concat(final1_parts, ignore_index=True)
    final1_path = frozen_dir / "final_combo1_raw_reference.parquet"
    final1.to_parquet(final1_path, index=False)

    child_as_core = child.rename(columns={"combo_id": "candidate_id", "raw_risk_state": "risk_state", "valid": "valid_signal"})[["candidate_id", "date", "active_count", "risk_state", "valid_signal", "risk_start", "risk_end"]]
    final2_parts = []
    for row in final.loc[final.model_family.eq("COMBO2")].itertuples(index=False):
        ids = child_map.loc[child_map.parent_combo2_id.eq(row.candidate_id)].sort_values("child_order").child_combo1_id.tolist()
        final2_parts.append(combine(child_as_core, row.candidate_id, ids, int(row.K), int(row.L), evaluation_start))
    final2 = pd.concat(final2_parts, ignore_index=True)
    final2_path = frozen_dir / "final_combo2_raw_reference.parquet"
    final2.to_parquet(final2_path, index=False)

    t1 = pd.concat([final_t1(group) for _, group in pd.concat([final1, final2], ignore_index=True).groupby("combo_id", sort=True)], ignore_index=True)
    t1_path = frozen_dir / "final_t1_reference.parquet"
    t1.to_parquet(t1_path, index=False)

    frozen = pd.read_parquet(frozen_path)
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.normalize()
    benchmark = frozen[["date", "kosdaq_close", "kosdaq_performance_calendar_eligible"]].copy()
    benchmark["benchmark_return"] = benchmark.kosdaq_close.pct_change().fillna(0.0)
    benchmark_path = frozen_dir / "benchmark_performance_reference.parquet"
    benchmark.to_parquet(benchmark_path, index=False)

    assets = [
        asset_entry("RUNTIME_FROZEN_INPUT", frozen_path, frozen, ["date"], "RUNTIME_INPUT", d01["research_sources"]["frozen_parquet"]),
        asset_entry("SIGNAL_DEFINITIONS", definition_path, definitions, ["candidate_id"], "RUNTIME_INPUT", d01["research_sources"]["candidate_metadata"]),
        asset_entry("CORE_PARITY_REFERENCE", core_path, core, ["candidate_id", "date"], "PARITY_REFERENCE_ONLY", {"matrix_files": d01["required_matrix_files"]}),
        asset_entry("CHILD_RAW_PARITY_REFERENCE", child_path, child, ["combo_id", "date"], "PARITY_REFERENCE_ONLY", {"source": "KQ3 state matrices + locked child mapping"}),
        asset_entry("FINAL_COMBO1_RAW_REFERENCE", final1_path, final1, ["combo_id", "date"], "PARITY_REFERENCE_ONLY", {"source": "KQ3 state matrices + locked final contract"}),
        asset_entry("FINAL_COMBO2_RAW_REFERENCE", final2_path, final2, ["combo_id", "date"], "PARITY_REFERENCE_ONLY", {"source": "locked child raw reference + final contract"}),
        asset_entry("FINAL_T1_REFERENCE", t1_path, t1, ["combo_id", "date"], "PARITY_REFERENCE_ONLY", {"source": "locked final raw references"}),
        asset_entry("BENCHMARK_REFERENCE", benchmark_path, benchmark, ["date"], "RUNTIME_FROZEN_HISTORY", d01["research_sources"]["frozen_parquet"]),
    ]
    manifest = {
        "contract_version": "kosdaq_macro7_frozen_assets_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "frozen_cutoff": "2026-07-28",
        "frozen_source_layer": "FINAL_FROZEN_INPUT: KQ2 quality/availability-aligned snapshot; no second availability lag permitted",
        "d0_contract_hashes": d01["d0_contract_files_sha256"],
        "d01_provenance_sha256": sha256(D01),
        "canonical_semantic_hash": {"row_order": "explicit sort keys per asset", "datetime": "YYYY-MM-DD", "nan": "<NA>", "float": "%.17g", "index_included": False, "rounding": "none"},
        "assets": assets,
        "invalid_state_semantics": d01["invalid_state_semantics_contract"],
    }
    manifest_path = ASSETS / "kosdaq_macro7_frozen_asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"assets": len(assets), "required_candidates": len(definitions), "core_rows": len(core), "child_rows": len(child)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
