"""Build dashboard-owned S&P Proxy-only Final10 Frozen replay assets.

This is a one-way build step: it reads the pinned research artifacts and writes
only ``spx_macro9_assets``. Runtime code never reads the research repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_snp")
ASSET_ROOT = DASHBOARD_ROOT / "spx_macro9_assets"
FROZEN_ROOT = ASSET_ROOT / "frozen"
STAGE1_PATH = DASHBOARD_ROOT / "reports" / "spx_macro9_stage1_contract_freeze.json"
OFFICIAL_START = pd.Timestamp("2008-04-01")
OFFICIAL_END = pd.Timestamp("2026-08-21")
OFFICIAL_DAYS = 4628


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unpack_state(value: object, days: int = OFFICIAL_DAYS) -> np.ndarray:
    if not isinstance(value, (bytes, bytearray)):
        raise TypeError("Expected packed official T+1 state bytes")
    values = np.unpackbits(np.frombuffer(value, dtype=np.uint8), bitorder="little")[:days]
    if len(values) != days:
        raise ValueError("Packed official T+1 state length mismatch")
    return values.astype(np.int8)


def _write_parquet(frame: pd.DataFrame, path: Path, outputs: dict[str, dict[str, object]]) -> None:
    frame.to_parquet(path, index=False)
    outputs[str(path.relative_to(ASSET_ROOT))] = {
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
    }


def _final_combo2_reference(contract: dict[str, object]) -> pd.DataFrame:
    practical_path = RESEARCH_ROOT / "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/practical_review30.parquet"
    performance_path = RESEARCH_ROOT / "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/performance_review30.parquet"
    source = pd.concat([pd.read_parquet(practical_path), pd.read_parquet(performance_path)], ignore_index=True)
    records: list[dict[str, object]] = []
    for item in contract["final_combo2"]:
        candidate_id = str(item["candidate_id"])
        row = source.loc[source["combo2_candidate_id"].astype(str).eq(candidate_id)]
        if len(row) != 1:
            raise ValueError(f"Final Combo2 reference unresolved: {candidate_id}")
        record = row.iloc[0].to_dict()
        record["candidate_id"] = candidate_id
        record["family"] = "Combo2"
        records.append(record)
    return pd.DataFrame(records)


def build() -> dict[str, object]:
    if ASSET_ROOT.exists():
        raise RuntimeError(f"Refusing to overwrite existing asset directory: {ASSET_ROOT}")
    stage1 = json.loads(STAGE1_PATH.read_text(encoding="utf-8"))
    canonical = stage1["proxy_only_source_contract"]["canonical_signal_bank"]
    canonical_path = RESEARCH_ROOT / str(canonical["path"])
    if sha256(canonical_path) != str(canonical["sha256"]):
        raise RuntimeError("Canonical Proxy-only Core15 index SHA mismatch")
    index = json.loads(canonical_path.read_text(encoding="utf-8"))
    if index["official_period"]["trading_days"] != OFFICIAL_DAYS:
        raise RuntimeError("Official period length mismatch")

    material_path = RESEARCH_ROOT / "outputs/snp/combo2/material_input/proxy_only_combo1_material_band_balanced_20260904T043000Z/combo2_material_input.parquet"
    material = pd.read_parquet(material_path)
    material = material.set_index("material_index", verify_integrity=True)
    required_indices = sorted({index for item in stage1["final_combo2"] for index in item["material_indices"]})
    selected_material = material.loc[required_indices].copy().reset_index()
    if len(selected_material) != len(required_indices):
        raise RuntimeError("Final Combo2 material child resolution mismatch")

    expected_child_by_index = {
        index: child
        for item in stage1["final_combo2"]
        for index, child in zip(item["material_indices"], item["child_combo1_ids"], strict=True)
    }
    for row in selected_material.itertuples(index=False):
        if str(row.material_combo1_id) != expected_child_by_index[int(row.material_index)]:
            raise RuntimeError(f"Material child mismatch at index {row.material_index}")

    final_combo1 = pd.DataFrame(stage1["final_combo1"])
    core_ids = set()
    for value in final_combo1["component_ids"]:
        core_ids.update(value)
    for value in selected_material["candidate_ids_key"].astype(str):
        core_ids.update(value.split("|"))
    core_ids = sorted(core_ids)

    partition_by_indicator = {str(item["indicator_id"]): item for item in index["partitions"]}
    core_raw = pd.DataFrame()
    core_t1 = pd.DataFrame()
    core_valid = pd.DataFrame()
    for indicator, ids in pd.Series(core_ids).groupby(pd.Series(core_ids).str.split("__").str[1], sort=True):
        partition = partition_by_indicator.get(str(indicator))
        if partition is None:
            raise RuntimeError(f"Core15 partition missing for {indicator}")
        source_path = RESEARCH_ROOT / str(partition["path"])
        if sha256(source_path) != str(partition["sha256"]):
            raise RuntimeError(f"Core15 partition SHA mismatch: {indicator}")
        candidates = list(ids)
        columns = ["date"] + [f"raw__{item}" for item in candidates] + [f"t1__{item}" for item in candidates] + [f"valid__{item}" for item in candidates]
        frame = pd.read_parquet(source_path, columns=columns)
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        frame = frame.loc[(frame["date"] >= OFFICIAL_START) & (frame["date"] <= OFFICIAL_END)].copy()
        if len(frame) != OFFICIAL_DAYS:
            raise RuntimeError(f"Core15 official date length mismatch: {indicator}")
        raw_part = frame[["date"] + [f"raw__{item}" for item in candidates]].rename(columns={f"raw__{item}": item for item in candidates})
        t1_part = frame[["date"] + [f"t1__{item}" for item in candidates]].rename(columns={f"t1__{item}": item for item in candidates})
        valid_part = frame[["date"] + [f"valid__{item}" for item in candidates]].rename(columns={f"valid__{item}": item for item in candidates})
        core_raw = raw_part if core_raw.empty else core_raw.merge(raw_part, on="date", how="inner", validate="one_to_one")
        core_t1 = t1_part if core_t1.empty else core_t1.merge(t1_part, on="date", how="inner", validate="one_to_one")
        core_valid = valid_part if core_valid.empty else core_valid.merge(valid_part, on="date", how="inner", validate="one_to_one")
    core_raw = core_raw.sort_values("date", kind="mergesort").reset_index(drop=True)
    core_t1 = core_t1.sort_values("date", kind="mergesort").reset_index(drop=True)
    core_valid = core_valid.sort_values("date", kind="mergesort").reset_index(drop=True)
    if len(core_t1) != OFFICIAL_DAYS or not core_t1["date"].equals(core_valid["date"]) or not core_raw["date"].equals(core_valid["date"]):
        raise RuntimeError("Core15 selected state/validity calendar mismatch")

    raw_cache_path = RESEARCH_ROOT / "outputs/snp/combo2/c2_1_material100_20260904_preflight/material100_combo1_raw_source_history.npz"
    raw_cache = np.load(raw_cache_path)
    raw_dates = pd.to_datetime(raw_cache["dates"]).normalize()
    raw_bank = raw_cache["raw"].astype(np.int8)
    raw_material_ids = [str(item) for item in raw_cache["material_ids"]]
    if raw_bank.shape != (100, len(raw_dates)) or len(raw_dates) != 6699:
        raise RuntimeError("Combo2 child raw source-history cache schema mismatch")
    child_raw = pd.DataFrame({"date": raw_dates})
    for row in selected_material.itertuples(index=False):
        position = int(row.material_index)
        if raw_material_ids[position] != str(row.material_combo1_id):
            raise RuntimeError(f"Combo2 child raw material identity mismatch: {position}")
        child_raw[str(row.material_combo1_id)] = raw_bank[position]

    operability_path = RESEARCH_ROOT / "outputs/snp/snp_combo_operability_first_finalist10_20260906_r3/operability_first_finalist10_all_groups.parquet"
    operability = pd.read_parquet(operability_path)
    final_c1_rows: list[dict[str, object]] = []
    for item in stage1["final_combo1"]:
        candidate_id = str(item["candidate_id"])
        row = operability.loc[operability["candidate_id"].astype(str).eq(candidate_id)]
        if len(row) != 1:
            raise ValueError(f"Final Combo1 reference unresolved: {candidate_id}")
        record = row.iloc[0].to_dict()
        record["candidate_id"] = candidate_id
        record["family"] = "Combo1"
        final_c1_rows.append(record)
    final_c1_reference = pd.DataFrame(final_c1_rows)
    final_c2_reference = _final_combo2_reference(stage1)
    final_combo1_reference = pd.DataFrame({"date": core_t1.loc[core_t1["date"] >= pd.Timestamp("2013-10-03"), "date"].reset_index(drop=True)})
    for row in final_c1_reference.itertuples(index=False):
        final_combo1_reference[str(row.candidate_id)] = unpack_state(row.official_t1_state_packed, days=len(final_combo1_reference))
    final_combo2_reference = pd.DataFrame({"date": core_t1["date"]})
    for row in final_c2_reference.itertuples(index=False):
        final_combo2_reference[str(row.candidate_id)] = unpack_state(row.official_t1_state_packed_rebuilt)

    metric_columns = [
        "candidate_id", "family", "K", "L", "cagr", "mdd", "calmar", "total_return",
        "risk_off_ratio", "transition_count", "risk_off_cycle_count", "short_cycle_20d_ratio",
        "official_t1_hash", "official_t1_hash_rebuilt",
    ]
    metrics = pd.concat([final_c1_reference, final_c2_reference], ignore_index=True)[metric_columns]
    metrics["official_t1_hash"] = metrics["official_t1_hash"].fillna(metrics["official_t1_hash_rebuilt"])
    metrics = metrics.drop(columns=["official_t1_hash_rebuilt"]).sort_values("candidate_id", kind="mergesort").reset_index(drop=True)
    metrics["metric_period"] = metrics["family"].map({"Combo1": "DEVELOPMENT_2013-10-03_TO_2026-08-21", "Combo2": "OFFICIAL_2008-04-01_TO_2026-08-21"})

    panel_path = RESEARCH_ROOT / "data/frozen/snp/snapshot_sp2_20260823T040000Z/snp_core15_inputs.parquet"
    panel = pd.read_parquet(panel_path, columns=["date", "close", "performance_calendar_eligible"])
    panel["date"] = pd.to_datetime(panel["date"]).dt.normalize()
    benchmark = panel.loc[(panel["date"] >= pd.Timestamp("2008-03-31")) & (panel["date"] <= OFFICIAL_END)].copy()
    benchmark = benchmark.sort_values("date", kind="mergesort").reset_index(drop=True)
    official = benchmark.loc[
        (benchmark["date"] >= OFFICIAL_START) & benchmark["performance_calendar_eligible"].astype(bool)
    ].copy()
    if len(official) != OFFICIAL_DAYS:
        raise RuntimeError("Benchmark official calendar mismatch")

    ASSET_ROOT.mkdir()
    FROZEN_ROOT.mkdir()
    outputs: dict[str, dict[str, object]] = {}
    _write_parquet(core_raw, FROZEN_ROOT / "core15_selected_reference_raw_state.parquet", outputs)
    _write_parquet(core_t1, FROZEN_ROOT / "core15_selected_reference_t1_state.parquet", outputs)
    _write_parquet(core_valid, FROZEN_ROOT / "core15_selected_reference_valid_signal.parquet", outputs)
    _write_parquet(child_raw, FROZEN_ROOT / "combo2_required_child_raw_state.parquet", outputs)
    _write_parquet(final_combo1_reference, FROZEN_ROOT / "final_combo1_reference_t1_state.parquet", outputs)
    _write_parquet(final_combo2_reference, FROZEN_ROOT / "final_combo2_reference_t1_state.parquet", outputs)
    _write_parquet(metrics, FROZEN_ROOT / "final10_frozen_replay_metrics.parquet", outputs)
    _write_parquet(benchmark, FROZEN_ROOT / "frozen_spx_benchmark_close.parquet", outputs)
    _write_parquet(selected_material.reset_index(drop=True), FROZEN_ROOT / "combo2_required_material_children.parquet", outputs)
    _write_parquet(final_combo1, FROZEN_ROOT / "final_combo1_definitions.parquet", outputs)

    final10 = pd.DataFrame([
        {"candidate_id": item["candidate_id"], "family": "Combo1", "display_order": order, "display_role": item["display_role"], "K": item["K"], "L": item["L"], "n_or_m": item["n"]}
        for order, item in enumerate(stage1["final_combo1"], start=1)
    ] + [
        {"candidate_id": item["candidate_id"], "family": "Combo2", "display_order": order, "display_role": item["display_role"], "K": item["K"], "L": item["L"], "n_or_m": item["m"]}
        for order, item in enumerate(stage1["final_combo2"], start=1)
    ])
    final10_path = ASSET_ROOT / "spx_macro9_final10.csv"
    final10.to_csv(final10_path, index=False)
    outputs[str(final10_path.relative_to(ASSET_ROOT))] = {"sha256": sha256(final10_path), "rows": int(len(final10)), "columns": list(final10.columns)}

    manifest = {
        "version": "spx_macro9_frozen_asset_manifest_v1",
        "status": "PASS_SPX_MACRO9_STAGE2_FROZEN_ASSETS_BUILT",
        "runtime_dependency": "DASHBOARD_OWNED_ASSETS_ONLY",
        "periods": {"combo1_display_metrics": {"start": "2013-10-03", "end": str(OFFICIAL_END.date()), "trading_days": 3240}, "combo2_display_metrics": {"start": str(OFFICIAL_START.date()), "end": str(OFFICIAL_END.date()), "trading_days": OFFICIAL_DAYS}},
        "stage1_contract": {"path": str(STAGE1_PATH.relative_to(DASHBOARD_ROOT)), "sha256": sha256(STAGE1_PATH)},
        "research_provenance": {
            "final10_workbook": stage1["authoritative_final10"],
            "canonical_proxy_only_index": {"path": str(canonical["path"]), "sha256": str(canonical["sha256"])},
            "material_children": {"path": str(material_path.relative_to(RESEARCH_ROOT)), "sha256": sha256(material_path)},
            "child_raw_source_history": {"path": str(raw_cache_path.relative_to(RESEARCH_ROOT)), "sha256": sha256(raw_cache_path)},
            "finalist_reference": {"path": str(operability_path.relative_to(RESEARCH_ROOT)), "sha256": sha256(operability_path)},
            "combo2_practical_reference": {"path": "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/practical_review30.parquet", "sha256": sha256(RESEARCH_ROOT / "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/practical_review30.parquet")},
            "combo2_performance_reference": {"path": "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/performance_review30.parquet", "sha256": sha256(RESEARCH_ROOT / "outputs/snp/combo2/snp_combo2_final_cross_m_stage3_20260906_r1/performance_review30.parquet")},
            "benchmark_panel": {"path": str(panel_path.relative_to(RESEARCH_ROOT)), "sha256": sha256(panel_path)},
        },
        "semantics": {
            "combo2_input": "CHILD_COMBO1_RAW_RISK_STATE",
            "frozen_replay_alignment": "child official T+1 at D equals child raw state at D-1; final Combo2 official T+1 at D is rebuilt from that prior-day child raw state without an additional shift",
            "final_t1_application_count": 1,
            "metric_periods_are_preserved_per_family": True,
            "invalid_is_not_risk_on": True,
            "proxy_only": True,
            "direct_oas_or_stitching": "FORBIDDEN",
            "cost_bps": 0,
            "cash_return": 0,
        },
        "counts": {"final_combo1": 5, "final_combo2": 5, "required_core_candidates": len(core_ids), "required_combo2_children": len(selected_material)},
        "outputs": outputs,
    }
    manifest_path = FROZEN_ROOT / "spx_macro9_frozen_asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps({"status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
