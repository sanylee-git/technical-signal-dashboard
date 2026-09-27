from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SINGLE_RUN = ROOT / "divergence_analysis/runs/run_20260927T131640Z_snp2_ndx_shell_preflight_single"
PARENT_RUN = ROOT / "divergence_analysis/runs/run_20260927T171600Z_snp2_combo2_n4_n15_parent_pool_robust_similarity"
SELECTION_RUN = ROOT / "divergence_analysis/runs/run_20260927T182622Z_snp2_strict_us_v21_tier100_selection"
OUT = ROOT / "spx_macro9_assets/trial_combo1_3"
SELECTED_IDS = (
    "3e12d084c6d477f9341a659b",
    "1cb2304e4f83508d7d20b788",
    "9b0bf6eb468f0e0f9ead4022",
)
EXPECTED_INPUTS = {
    "snp_source_panel.parquet": "a9c52bc872f12e965fd43bfa2791d444206807775b2a01ee0eb944ad1d7f2160",
    "snp_single69_registry.parquet": "745c55e7a6465f110f500386e3b32069cdb6fb49b3cd14260897194c9857f558",
    "single_raw_state.parquet": "06590b64676672a1097808b05b820a831c9fb65f242f062080aa2a72504eb96c",
    "single_raw_valid.parquet": "7e3cd2ba5a7205e4e245aee81e68351211a37feb27853c3d656fc764f276cce7",
    "single_raw_events_long.parquet": "1d3ad871b84c234a6457eb7e3206e0b193a9862815f61a50020c74794c37e76f",
    "single_official_t1.parquet": "9e86c63798f3e81daed81d07bcb7dfc293721924a18f2c4098015241b3d8ccf6",
    "official_t1_states.npz": "f75335a6844e2f99046082fc31295e649b7073ed0ec315e232222c371d1e2e52",
    "strict_pool_tier100_selected.csv": "00e898f13ee4f4811e5c918b583ff04a3f9d106b1fbd034dd03c9afdd2a23c54",
    "run_single_preflight.py": "a452b70054602f17e166a0c40fb09e7fb95e19505e886ac6468098f58eafe009",
}
EVALUATION_START = pd.Timestamp("2008-04-01")
EVALUATION_END = pd.Timestamp("2026-08-21")
FAMILY_LABELS = {
    "Global Credit Stress": "신용스트레스",
    "Bollinger": "S&P500 볼린저",
    "Breadth": "시장 breadth",
    "HV": "HV",
    "S&P 500 Index Level": "S&P500 지수",
    "S&P 500 RSI": "S&P500 RSI",
    "NATR": "NATR",
    "10Y-2Y": "10Y-2Y 스프레드",
    "10Y-3M": "10Y-3M 스프레드",
    "10Y Nominal Yield Slope": "10Y 금리기울기",
    "10Y Real Yield": "10Y 실질금리",
    "HY OAS": "HY OAS",
    "IG OAS": "IG OAS",
    "VIX": "VIX",
    "VIX Spread": "VIX 스프레드",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_preflight_module(path: Path):
    spec = importlib.util.spec_from_file_location("snp2_corrected_single_preflight", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Corrected Single69 helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hysteresis_reference(active: np.ndarray, valid: np.ndarray, k: int, l: int) -> np.ndarray:
    time = np.arange(len(active), dtype=np.int64)
    last_invalid = np.maximum.accumulate(np.where(valid, -1, time))
    eligible = time > last_invalid
    starts = eligible & (active >= k)
    ends = eligible & (active <= l)
    last_start = np.maximum.accumulate(np.where(starts, time, -1))
    last_end = np.maximum.accumulate(np.where(ends, time, -1))
    return (last_start > last_end).astype(np.uint8)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "trial_asset_manifest.json"
    if manifest_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing preview assets: {manifest_path}")

    paths = {
        "snp_source_panel.parquet": SINGLE_RUN / "01_inputs/snp_source_panel.parquet",
        "snp_single69_registry.parquet": SINGLE_RUN / "01_inputs/snp_single69_registry.parquet",
        "single_raw_state.parquet": SINGLE_RUN / "02_single/single_raw_state.parquet",
        "single_raw_valid.parquet": SINGLE_RUN / "02_single/single_raw_valid.parquet",
        "single_raw_events_long.parquet": SINGLE_RUN / "02_single/single_raw_events_long.parquet",
        "single_official_t1.parquet": SINGLE_RUN / "02_single/single_official_t1.parquet",
        "official_t1_states.npz": PARENT_RUN / "03_state/official_t1_states.npz",
        "strict_pool_tier100_selected.csv": SELECTION_RUN / "strict_pool_tier100_selected.csv",
        "run_single_preflight.py": SINGLE_RUN / "run_single_preflight.py",
    }
    input_hashes = {name: sha256(path) for name, path in paths.items()}
    mismatches = {name: (input_hashes[name], EXPECTED_INPUTS[name]) for name in paths if input_hashes[name] != EXPECTED_INPUTS[name]}
    if mismatches:
        raise RuntimeError(f"Pinned input SHA mismatch: {mismatches}")

    helper = load_preflight_module(paths["run_single_preflight.py"])
    panel = pd.read_parquet(paths["snp_source_panel.parquet"]).sort_values("date", kind="mergesort").reset_index(drop=True)
    registry = pd.read_parquet(paths["snp_single69_registry.parquet"]).sort_values("candidate_id", kind="mergesort").reset_index(drop=True)
    raw = pd.read_parquet(paths["single_raw_state.parquet"]).sort_values("date", kind="mergesort").reset_index(drop=True)
    valid = pd.read_parquet(paths["single_raw_valid.parquet"]).sort_values("date", kind="mergesort").reset_index(drop=True)
    event_reference = pd.read_parquet(paths["single_raw_events_long.parquet"])
    official_reference = pd.read_parquet(paths["single_official_t1.parquet"])
    selected = pd.read_csv(paths["strict_pool_tier100_selected.csv"])
    panel_dates = pd.DatetimeIndex(pd.to_datetime(panel["date"]).dt.normalize())
    raw_dates = pd.DatetimeIndex(pd.to_datetime(raw["date"]).dt.normalize())
    if len(registry) != 69 or registry.candidate_id.duplicated().any():
        raise RuntimeError("Single69 registry count/uniqueness mismatch")
    if not panel_dates.equals(raw_dates) or not raw_dates.equals(pd.DatetimeIndex(pd.to_datetime(valid["date"]).dt.normalize())):
        raise RuntimeError("Single69 panel/raw/valid calendar mismatch")
    if not panel_dates.is_monotonic_increasing or panel_dates.duplicated().any():
        raise RuntimeError("Source panel calendar is not unique and sorted")
    if not set(SELECTED_IDS).issubset(set(selected.candidate_id.astype(str))):
        raise RuntimeError("The requested 3 candidate IDs are not present in the strict 300")
    selected = selected.set_index("candidate_id").loc[list(SELECTED_IDS)].reset_index()
    if selected.short_tier.tolist() != ["T1_00_10", "T2_10_20", "T3_20_30"]:
        raise RuntimeError("Selected candidate tier mapping changed")
    if selected[["tier4_effective_miss", "tier3_effective_miss", "correction_effective_miss"]].to_numpy().any():
        raise RuntimeError("Requested candidate violates the strict miss filter")

    eval_mask = panel["performance_calendar_eligible"].astype(bool) & panel_dates.to_series(index=panel.index).between(EVALUATION_START, EVALUATION_END).to_numpy()
    eval_dates = pd.DatetimeIndex(panel_dates[eval_mask])
    if len(eval_dates) != 4628 or eval_dates[0] != EVALUATION_START or eval_dates[-1] != EVALUATION_END:
        raise RuntimeError("Frozen evaluation calendar mismatch")
    positions = panel_dates.get_indexer(eval_dates)
    if (positions < 1).any():
        raise RuntimeError("Official T+1 predecessor is missing from the source calendar")

    archive = np.load(paths["official_t1_states.npz"], allow_pickle=True)
    archive_ids = [str(value) for value in archive["combo1_id"].tolist()]
    archive_dates = pd.DatetimeIndex(pd.to_datetime(archive["dates"]).normalize())
    archive_states = archive["state"]
    if archive_states.shape != (len(archive_ids), len(archive_dates)) or not archive_dates.equals(eval_dates):
        raise RuntimeError("Authoritative Combo1 state archive schema/calendar mismatch")
    archive_row = {candidate_id: index for index, candidate_id in enumerate(archive_ids)}

    raw_lookup = raw.set_index("date")
    valid_lookup = valid.set_index("date")
    registry_lookup = registry.set_index("candidate_id", drop=False)
    component_ids = list(dict.fromkeys("|".join(selected.candidate_ids_key.astype(str)).split("|")))
    if not set(component_ids).issubset(set(registry.candidate_id.astype(str))):
        raise RuntimeError("Selected Combo1 references a component outside Single69")
    calendar = panel_dates
    aligned_states: dict[str, np.ndarray] = {}
    chart_parts: list[pd.DataFrame] = []
    component_mismatch = 0
    transition_mismatch = 0
    event_lookup = event_reference.loc[event_reference.candidate_id.astype(str).isin(component_ids)].copy()
    event_lookup["date"] = pd.to_datetime(event_lookup["date"]).dt.normalize()

    for component_id in component_ids:
        record = registry_lookup.loc[component_id]
        detail = helper.detail_signal(panel, record)
        computed_raw, computed_valid, computed_start, computed_end = helper.align_signal(detail, calendar)
        stored_raw = pd.to_numeric(raw_lookup[component_id], errors="coerce").fillna(-1).to_numpy(dtype=np.int8)
        stored_valid = valid_lookup[component_id].fillna(False).astype(bool).to_numpy()
        component_mismatch += int(np.count_nonzero(computed_raw != stored_raw))
        component_mismatch += int(np.count_nonzero(computed_valid != stored_valid))
        reference_events = event_lookup.loc[event_lookup.candidate_id.astype(str).eq(component_id)].set_index("date").reindex(calendar)
        ref_start = reference_events["risk_start"].fillna(False).astype(bool).to_numpy()
        ref_end = reference_events["risk_end"].fillna(False).astype(bool).to_numpy()
        transition_mismatch += int(np.count_nonzero(computed_start != ref_start))
        transition_mismatch += int(np.count_nonzero(computed_end != ref_end))
        aligned_states[component_id] = stored_raw

        detail_index = pd.DatetimeIndex(pd.to_datetime(detail.index).normalize())
        chart = detail.copy()
        chart.index = detail_index
        chart = chart.loc[~chart.index.duplicated(keep="last")].reindex(eval_dates)
        chart.insert(0, "date", eval_dates)
        chart.insert(0, "component_id", component_id)
        chart["risk_state"] = stored_raw[positions]
        chart["risk_start"] = computed_start[positions]
        chart["risk_end"] = computed_end[positions]
        chart["valid_signal"] = stored_valid[positions]
        chart["indicator_family"] = str(record.indicator_family)
        chart["indicator_id"] = str(record.indicator_id)
        chart["component_label"] = f"{FAMILY_LABELS.get(str(record.indicator_family), str(record.indicator_family))} · {component_id.rsplit('__', 1)[-1]}"
        chart_parts.append(chart.reset_index(drop=True))

    if component_mismatch or transition_mismatch:
        raise RuntimeError(f"Component display parity failed: raw/valid={component_mismatch}, transitions={transition_mismatch}")

    candidate_history_parts: list[pd.DataFrame] = []
    component_history_parts: list[pd.DataFrame] = []
    candidate_rows: list[dict[str, object]] = []
    candidate_state_mismatch = 0
    for order, row in selected.iterrows():
        candidate_id = str(row.candidate_id)
        ids = str(row.candidate_ids_key).split("|")
        n, k, l = int(row.n), int(row.K), int(row.L)
        if len(ids) != n or len(set(ids)) != n:
            raise RuntimeError(f"Candidate component count/uniqueness mismatch: {candidate_id}")
        component_raw = np.vstack([aligned_states[value] for value in ids]).astype(np.int16)
        component_valid = np.vstack([valid_lookup[value].fillna(False).astype(bool).to_numpy() for value in ids])
        effective_valid = component_valid & (component_raw >= 0)
        active_full = np.where(effective_valid, component_raw, 0).sum(axis=0, dtype=np.int16)
        all_valid = effective_valid.all(axis=0)
        candidate_raw_full = hysteresis_reference(active_full, all_valid, k, l)
        expected_official = candidate_raw_full[positions - 1].astype(np.uint8)
        archived_official = archive_states[archive_row[candidate_id]].astype(np.uint8)
        candidate_state_mismatch += int(np.count_nonzero(expected_official != archived_official))
        expected_hash = str(row.official_t1_state_sha256)
        actual_hash = hashlib.sha256(np.packbits(archived_official, bitorder="little").tobytes()).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(f"Candidate official T+1 SHA mismatch: {candidate_id}")
        if (archived_official > 1).any() or not all_valid[positions - 1].all():
            raise RuntimeError(f"Candidate official state has invalid cells: {candidate_id}")

        state = archived_official.astype(np.int8)
        previous = np.r_[state[0], state[:-1]]
        starts = (state == 1) & (previous == 0)
        ends = (state == 0) & (previous == 1)
        active_official = active_full[positions - 1]
        candidate_history_parts.append(pd.DataFrame({
            "candidate_id": candidate_id,
            "date": eval_dates,
            "strategy_risk_state": state,
            "previous_strategy_risk_state": previous,
            "active_count": active_official,
            "risk_start": starts,
            "risk_end": ends,
            "valid": True,
        }))
        for component_order, component_id in enumerate(ids, start=1):
            source = next(part for part in chart_parts if str(part.component_id.iloc[0]) == component_id)
            component_history_parts.append(pd.DataFrame({
                "parent_candidate_id": candidate_id,
                "component_id": component_id,
                "component_order": component_order,
                "component_kind": "CORE_INDICATOR",
                "component_label": source.component_label.iloc[0],
                "date": eval_dates,
                "component_risk_state": aligned_states[component_id][positions],
                "component_valid": valid_lookup[component_id].fillna(False).astype(bool).to_numpy()[positions],
                "risk_start": source.risk_start.to_numpy(dtype=bool),
                "risk_end": source.risk_end.to_numpy(dtype=bool),
            }))
        candidate_rows.append({
            "candidate_id": candidate_id,
            "family": "Combo1",
            "model_family": "COMBO1",
            "display_order": order + 1,
            "display_role": f"{row.short_tier} · V2.1 rank {int(row['rank'])}",
            "selection_rank": int(row["rank"]),
            "short_tier": str(row.short_tier),
            "n": n,
            "K": k,
            "L": l,
            "component_ids_key": "|".join(ids),
            "cagr": float(row.cagr),
            "mdd": float(row.mdd),
            "calmar": float(row.cagr / abs(row.mdd)) if float(row.mdd) else np.nan,
            "raw_risk_off_cycle_count": int(row.raw_risk_off_cycle_count),
            "raw_short_cycle_20d_ratio": float(row.raw_short_cycle_20d_ratio),
            "tier4_effective_miss": int(row.tier4_effective_miss),
            "tier3_effective_miss": int(row.tier3_effective_miss),
            "correction_effective_miss": int(row.correction_effective_miss),
            "costly_false_alarm_63_rate": float(row.costly_false_alarm_63_rate),
            "major_recovery_median": float(row.major_recovery_median),
            "official_t1_state_sha256": actual_hash,
        })

    if candidate_state_mismatch:
        raise RuntimeError(f"Combo1 official T+1 full-period mismatch: {candidate_state_mismatch}")
    candidate_history = pd.concat(candidate_history_parts, ignore_index=True)
    component_history = pd.concat(component_history_parts, ignore_index=True)
    component_chart_history = pd.concat(chart_parts, ignore_index=True)
    benchmark_history = panel.loc[eval_mask, ["date", "close"]].copy()
    benchmark_history["date"] = pd.to_datetime(benchmark_history["date"]).dt.normalize()
    candidate_metrics = pd.DataFrame(candidate_rows)
    candidate_metrics["basis_date"] = EVALUATION_END
    candidate_metrics["availability_status"] = "FROZEN_ONLY"
    candidate_metrics["status"] = "USABLE"
    candidate_metrics["raw_risk_state"] = candidate_history.groupby("candidate_id", sort=False).tail(1).set_index("candidate_id").loc[candidate_metrics.candidate_id, "strategy_risk_state"].to_numpy()
    candidate_metrics["invest_position"] = 1 - candidate_metrics["raw_risk_state"].astype(int)

    output_frames = {
        "candidate_history.parquet": candidate_history,
        "component_history.parquet": component_history,
        "component_chart_history.parquet": component_chart_history,
        "benchmark_history.parquet": benchmark_history,
        "candidate_metrics.parquet": candidate_metrics,
    }
    for name, frame in output_frames.items():
        frame.to_parquet(OUT / name, index=False)

    manifest = {
        "status": "PASS_SNP2_COMBO1_TRIAL_FROZEN_ASSETS_READY",
        "mode": "FROZEN_VISUAL_VALIDATION_ONLY",
        "candidates": list(SELECTED_IDS),
        "candidate_tiers": dict(zip(candidate_metrics.candidate_id, candidate_metrics.short_tier)),
        "combo2_count": 0,
        "evaluation_period": [str(EVALUATION_START.date()), str(EVALUATION_END.date())],
        "evaluation_sessions": len(eval_dates),
        "strict_pool_criteria": {"tier4_effective_miss": 0, "tier3_effective_miss": 0, "correction_effective_miss": 0},
        "selection_order": "Per-tier top 100 from the strict pool by US V2.1 rank; page preview uses the user's T1/T2/T3 first-ranked examples.",
        "source_runs": {"single_preflight": SINGLE_RUN.name, "n4_n15_state_archive": PARENT_RUN.name, "strict_selection": SELECTION_RUN.name},
        "inputs": {name: {"path": str(path), "sha256": input_hashes[name], "bytes": path.stat().st_size} for name, path in paths.items()},
        "qa": {
            "single69_registry_count": len(registry) == 69,
            "selected_candidate_ids_exact": list(candidate_metrics.candidate_id) == list(SELECTED_IDS),
            "component_raw_valid_mismatch": component_mismatch,
            "component_transition_mismatch": transition_mismatch,
            "candidate_official_t1_mismatch": candidate_state_mismatch,
            "official_t1_application_count": 1,
            "additional_t1_application_count": 0,
            "candidate_state_hash_match": True,
            "candidate_invalid_state_cells": int((candidate_history.strategy_risk_state < 0).sum()),
            "component_lineage_complete": bool(component_history.component_id.notna().all()),
            "network_fetch": 0,
            "combo2_count": 0,
        },
        "outputs": {},
    }
    if not all(value is True for key, value in manifest["qa"].items() if isinstance(value, bool)):
        raise RuntimeError(f"Trial asset QA failed: {manifest['qa']}")
    if any(int(manifest["qa"][key]) != 0 for key in ("component_raw_valid_mismatch", "component_transition_mismatch", "candidate_official_t1_mismatch", "candidate_invalid_state_cells", "additional_t1_application_count", "network_fetch", "combo2_count")):
        raise RuntimeError(f"Trial asset mismatch/count QA failed: {manifest['qa']}")
    for name in output_frames:
        path = OUT / name
        manifest["outputs"][name] = {"sha256": sha256(path), "bytes": path.stat().st_size, "rows": len(output_frames[name])}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "candidates": candidate_rows, "qa": manifest["qa"], "assets": manifest["outputs"]}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
