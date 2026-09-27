"""Materialize the approved S&P2 operational 5+5 assets.

The research outputs remain read-only. This builder creates a dashboard-owned
operational namespace from the approved Single69 and Combo1/Combo2 definitions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "spx_macro9_assets"
OUT = ASSETS / "operational"
SINGLE_RUN = ROOT / "divergence_analysis/runs/run_20260925T145120Z_snp2_kospi_aligned_single69"
COMPRESSION_RUN = ROOT / "divergence_analysis/runs/run_20260927T_snp2_v211_candidate_compression_v6"
COMBO2_STATE = ROOT.parent / "macro_dashboard_snp/outputs/snp/combo2/final_selection/snp_c2_cross_m2_m12_tier_compression_20260926_r3/02_state/official_t1_state.npz"
PANEL_SOURCE = ROOT.parent / "macro_dashboard_snp/data/frozen/snp/snapshot_sp2_20260823T040000Z/snp_core15_inputs.parquet"
N8_N12 = ROOT / "divergence_analysis/runs/run_20260926T_n8_c15_m15_n9_n12_sequential_v1"
N13_N15 = ROOT / "divergence_analysis/runs/run_20260926T_n12_c16_m14_n13_n15_sequential_v3"

COMBO1_IDS = [
    ("1c1c7597686c9e0a92c22342", "Main1 밸런스형"),
    ("dc48a38a72c1ed1bb7c35213", "Main2 빠른복귀형"),
    ("20a398b847381b5b90486444", "저휩소형"),
    ("4851698f11598ca1988458e8", "큰위기방어형"),
    ("08cb9a31c7e4e3627e8801a0", "고성과형"),
]
COMBO2_IDS = [
    ("30d59a9bc0660ad8f05022e0", "Main1 밸런스형"),
    ("9542e4c75d39ba78d33f1771", "Main2 조기경보형"),
    ("9c74969a657d487a21698851", "빠른복귀형"),
    ("c793ab337024e4ffd35c3f9c", "저휩소형"),
    ("bc255fa19b22198946a3d4cd", "고성과형"),
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parent_path(n: int) -> Path:
    root = N8_N12 if n <= 12 else N13_N15
    run = root / f"N{n}" / "04_selection"
    name = "parent_candidates_c15_m15.parquet" if n <= 12 else "parent_candidates_c16_m14.parquet"
    return run / name


def _parent(n: int, short_id: str) -> pd.Series:
    frame = pd.read_parquet(_parent_path(n))
    rows = frame.loc[frame["candidate_set_id"].astype(str).eq(short_id)]
    if len(rows) != 1:
        raise RuntimeError(f"Combo1 child definition unresolved: n{n}:{short_id}")
    return rows.iloc[0]


def _make_registry(selected: pd.DataFrame) -> pd.DataFrame:
    source_columns = {
        "snp_index_level": ("close", "identity"),
        "us_hy_oas": ("hy_oas_safe", "identity"),
        "us_ig_oas": ("ig_oas_safe", "identity"),
        "global_credit_stress": ("global_credit_stress_safe", "identity"),
        "vix_level": ("vix", "negate"),
        "vix_spread": ("vix_spread_safe", "identity"),
        "us_10y_real_yield": ("real_yield_10y", "negate"),
        "us_10y_2y_spread": ("spread_10y2y", "identity"),
        "us_10y_3m_spread": ("spread_10y3m", "identity"),
        "snp_breadth": ("breadth_raw", "identity"),
    }
    engines = {
        "us_10y_nominal_yield_slope": "yield_slope_downside_crossing",
        "snp_bollinger": "bollinger_reentry",
        "snp_rsi": "rsi_state_transition",
    }
    rows = []
    for item in selected.itertuples(index=False):
        source, transform = source_columns.get(item.indicator_id, ("close", "identity"))
        engine = engines.get(item.indicator_id, "level_downside_crossing")
        direction = "exception" if engine in {"bollinger_reentry", "rsi_state_transition"} else "higher_is_safer"
        if item.indicator_id == "snp_breadth":
            direction = "higher_is_safer_no_inversion"
        rows.append({
            "candidate_id": str(item.candidate_id),
            "indicator_id": str(item.indicator_id),
            "indicator_family": str(item.indicator_family),
            "params_json": str(item.params_json),
            "engine": engine,
            "direction": direction,
            "candidate_valid_start_date": "2000-01-03",
            "official_period_fully_valid": True,
            "source_column": source,
            "transform": transform,
        })
    return pd.DataFrame(rows).sort_values("candidate_id", kind="mergesort").reset_index(drop=True)


def _make_final10(combo1: pd.DataFrame, combo2: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for order, (candidate_id, role) in enumerate(COMBO1_IDS, start=1):
        item = combo1.loc[combo1["candidate_id"].astype(str).eq(candidate_id)]
        if len(item) != 1:
            raise RuntimeError(f"Combo1 final candidate unresolved: {candidate_id}")
        item = item.iloc[0]
        key = str(item["candidate_ids_key"])
        rows.append({
            "candidate_id": candidate_id, "display_role": role, "research_lane": str(item.get("selection_lane", "PERFORMANCE")),
            "n": int(item["n"]), "K": int(item["K"]), "L": int(item["L"]), "component_ids": key.split("|"),
            "family": "Combo1", "selection_type": "Performance", "component_ids_key": key, "display_order": order,
            "n_or_m": int(item["n"]), "m": None, "material_indices": None, "child_combo1_ids": None,
        })
    for order, (candidate_id, role) in enumerate(COMBO2_IDS, start=1):
        item = combo2.loc[combo2["combo2_candidate_id"].astype(str).eq(candidate_id)]
        if len(item) != 1:
            raise RuntimeError(f"Combo2 final candidate unresolved: {candidate_id}")
        item = item.iloc[0]
        children = str(item["child_combo1_ids"])
        rows.append({
            "candidate_id": candidate_id, "display_role": role, "research_lane": str(item.get("selection_lane", "PERFORMANCE")),
            "n": None, "K": int(item["K"]), "L": int(item["L"]), "component_ids": None,
            "family": "Combo2", "selection_type": "Performance", "component_ids_key": None, "display_order": order,
            "n_or_m": int(item["m"]), "m": int(item["m"]), "material_indices": None, "child_combo1_ids": children,
        })
    return pd.DataFrame(rows)


def _make_children(combo2: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for parent_id, _role in COMBO2_IDS:
        parent = combo2.loc[combo2["combo2_candidate_id"].astype(str).eq(parent_id)].iloc[0]
        tokens = [token for token in str(parent["child_combo1_ids"]).split("|") if token]
        for order, token in enumerate(tokens, start=1):
            n_text, short_id = token.split(":", 1)
            child = _parent(int(n_text[1:]), short_id)
            rows.append({
                "parent_candidate_id": parent_id,
                "child_order": order,
                "child_canonical_parent_id": token,
                "child_n": int(child["n"]),
                "child_K": int(child["K"]),
                "child_L": int(child["L"]),
                "child_component_ids_key": str(child["candidate_ids_key"]),
            })
    return pd.DataFrame(rows)


def _make_raw_seed(panel: pd.DataFrame, official: pd.DataFrame) -> pd.DataFrame:
    panel_dates = pd.DatetimeIndex(pd.to_datetime(panel["date"]).dt.normalize())
    official = official.copy()
    official["date"] = pd.to_datetime(official["date"]).dt.normalize()
    positions = panel_dates.searchsorted(pd.DatetimeIndex(official["date"]), side="left") - 1
    if (positions < 0).any():
        raise RuntimeError("Cannot materialize authoritative raw seed before first official date")
    out = official.copy()
    out["date"] = panel_dates.take(positions)
    return out


def _make_combo2_reference(official: pd.DataFrame, combo2: pd.DataFrame) -> pd.DataFrame:
    source = __import__("numpy").load(COMBO2_STATE, allow_pickle=True)
    source_ids = source["candidate_id"].astype(str)
    source_state = source["state"].astype("int8", copy=False)
    dates = pd.DatetimeIndex(pd.to_datetime(official["date"]).dt.normalize())
    if source_state.shape[1] != len(dates):
        raise RuntimeError("Combo2 authoritative T+1 state calendar mismatch")
    rows = {str(row.combo2_candidate_id): row for row in combo2.itertuples(index=False)}
    output = pd.DataFrame({"date": dates})
    for candidate_id, _role in COMBO2_IDS:
        matches = __import__("numpy").flatnonzero(source_ids == candidate_id)
        if len(matches) != 1 or candidate_id not in rows:
            raise RuntimeError(f"Combo2 authoritative T+1 state unresolved: {candidate_id}")
        state = source_state[int(matches[0])]
        packed = __import__("numpy").packbits(state, bitorder="little").tobytes()
        expected = str(rows[candidate_id].official_t1_state_hash)
        actual = __import__("hashlib").sha256(packed).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Combo2 authoritative T+1 hash mismatch: {candidate_id}")
        output[candidate_id] = state
    return output


def _make_operational_panel() -> pd.DataFrame:
    """Materialize the exact Single69 research panel plus runtime-only fields."""
    panel = pd.read_parquet(PANEL_SOURCE).copy()
    panel["date"] = pd.to_datetime(panel["date"]).dt.normalize()
    panel = panel.sort_values("date", kind="mergesort").drop_duplicates("date", keep="last").reset_index(drop=True)
    panel["hy_raw_proxy"] = -pd.to_numeric(panel["hy_oas_safe"], errors="coerce")
    panel["ig_raw_proxy"] = -pd.to_numeric(panel["ig_oas_safe"], errors="coerce")
    panel["spx_performance_return"] = pd.to_numeric(panel["close"], errors="coerce").pct_change()
    panel["breadth_input_eligible"] = panel["breadth_raw"].gt(0).fillna(False)
    required = ["hy_oas_safe", "ig_oas_safe", "global_credit_stress_safe", "vix", "vix3m", "real_yield_10y", "spread_10y2y", "spread_10y3m", "dgs10"]
    panel["core15_input_eligible"] = panel[["ohlc_signal_eligible", "breadth_input_eligible"]].all(axis=1) & panel[required].notna().all(axis=1)
    return panel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(SINGLE_RUN / "05_selection/kospi_aligned_single69.parquet")
    official = pd.read_parquet(SINGLE_RUN / "03_states/selected_single69_official_t1.parquet")
    panel = _make_operational_panel()
    combo1 = pd.read_csv(COMPRESSION_RUN / "combo1/input_candidates.csv", low_memory=False)
    combo2 = pd.read_csv(COMPRESSION_RUN / "combo2/input_candidates.csv", low_memory=False)
    combo1 = combo1.loc[combo1["candidate_id"].astype(str).isin([x[0] for x in COMBO1_IDS])].copy()
    combo2 = combo2.loc[combo2["combo2_candidate_id"].astype(str).isin([x[0] for x in COMBO2_IDS])].copy()
    if len(selected) != 69 or len(official.columns) != 70 or len(combo1) != 5 or len(combo2) != 5:
        raise RuntimeError("Approved S&P2 operational input count gate failed")
    registry = _make_registry(selected)
    final10 = _make_final10(combo1, combo2)
    children = _make_children(combo2)
    raw_seed = _make_raw_seed(panel, official)
    combo2_reference = _make_combo2_reference(official, combo2)
    if set(children["child_component_ids_key"].str.split("|").explode()) - set(registry["candidate_id"]):
        raise RuntimeError("Combo2 child component is outside Single69 registry")
    for path, frame in (
        (OUT / "snp2_source_panel.parquet", panel),
        (OUT / "snp2_single69_registry.parquet", registry),
        (OUT / "snp2_single69_official_t1.parquet", official),
        (OUT / "snp2_single69_raw_seed.parquet", raw_seed),
        (OUT / "snp2_combo2_authoritative_t1.parquet", combo2_reference),
    ):
        frame.to_parquet(path, index=False)
    final10.to_csv(OUT / "snp2_final10.csv", index=False)
    children.to_csv(OUT / "snp2_combo2_child_mapping.csv", index=False)
    outputs = {}
    for path in sorted(OUT.iterdir()):
        outputs[str(path.relative_to(ASSETS))] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    manifest = {
        "status": "PASS_SPX2_OPERATIONAL_FINAL10_ASSETS_READY",
        "runtime_dependency": "SNP2_OPERATIONAL_NAMESPACE_ONLY",
        "source_lineage": {
            "single69_selection": str((SINGLE_RUN / "05_selection/kospi_aligned_single69.parquet").resolve()),
            "single69_selection_sha256": _sha256(SINGLE_RUN / "05_selection/kospi_aligned_single69.parquet"),
            "single69_official_t1": str((SINGLE_RUN / "03_states/selected_single69_official_t1.parquet").resolve()),
            "single69_official_t1_sha256": _sha256(SINGLE_RUN / "03_states/selected_single69_official_t1.parquet"),
            "candidate_compression_run": str(COMPRESSION_RUN.resolve()),
            "combo2_authoritative_t1": str(COMBO2_STATE.resolve()),
            "combo2_authoritative_t1_sha256": _sha256(COMBO2_STATE),
            "panel_source_path": str(PANEL_SOURCE.resolve()),
            "panel_source_sha256": _sha256(PANEL_SOURCE),
        },
        "contract": {
            "evaluation_period": "2008-04-01~2026-08-21",
            "single_count": 69,
            "final_combo1_count": 5,
            "final_combo2_count": 5,
            "combo2_default": "30d59a9bc0660ad8f05022e0",
            "official_t1_application_count": 1,
            "combo2_authoritative_t1_source": "read-only source state artifact; no UI-side recalculation",
            "legacy_final10_assets_loaded": False,
        },
        "outputs": outputs,
    }
    (ASSETS / "snp2_operational_asset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str((ASSETS / 'snp2_operational_asset_manifest.json').resolve()), "registry": len(registry), "final10": len(final10), "children": len(children)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
