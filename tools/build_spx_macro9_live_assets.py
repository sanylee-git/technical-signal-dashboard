"""Build S&P Macro9's dashboard-owned Proxy-only live-runtime inputs.

The builder is intentionally one-way: research artifacts are read once here;
the deployed runtime reads only the resulting ``spx_macro9_assets`` files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


DASHBOARD = Path(__file__).resolve().parents[1]
RESEARCH = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_snp")
ASSETS = DASHBOARD / "spx_macro9_assets"
FROZEN = ASSETS / "frozen"
STAGE1 = DASHBOARD / "reports" / "spx_macro9_stage1_contract_freeze.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(frame: pd.DataFrame, path: Path, records: dict[str, dict[str, object]]) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite existing asset: {path}")
    frame.to_parquet(path, index=False)
    records[str(path.relative_to(ASSETS))] = {
        "sha256": sha256(path), "rows": int(len(frame)), "columns": list(frame.columns),
    }


def _series(path: Path, column: str = "value") -> pd.Series:
    frame = pd.read_csv(path)
    return pd.Series(pd.to_numeric(frame[column], errors="coerce").to_numpy(), index=pd.to_datetime(frame["date"]).normalize())


def _asof(source: pd.Series, calendar: pd.DatetimeIndex, lag: int) -> tuple[pd.Series, pd.Series]:
    valid = source.dropna().sort_index()
    positions = calendar.searchsorted(valid.index, side="right") + max(0, lag - 1)
    accepted = positions < len(calendar)
    effective = pd.DataFrame({"effective": calendar.take(positions[accepted]), "observation": valid.index[accepted], "value": valid.iloc[np.flatnonzero(accepted)].to_numpy()})
    target = pd.DataFrame({"date": calendar})
    merged = pd.merge_asof(target, effective.sort_values("effective"), left_on="date", right_on="effective", direction="backward")
    return pd.Series(merged["value"].to_numpy(), index=calendar), pd.Series(pd.to_datetime(merged["observation"]).to_numpy(), index=calendar)


def _selected_core_ids(contract: dict[str, object], material: pd.DataFrame) -> list[str]:
    result: set[str] = set()
    for item in contract["final_combo1"]:
        result.update(item["component_ids"])
    for value in material["candidate_ids_key"].astype(str):
        result.update(value.split("|"))
    return sorted(result)


def build() -> dict[str, object]:
    contract = json.loads(STAGE1.read_text(encoding="utf-8"))
    panel_path = RESEARCH / "data/frozen/snp/snapshot_sp2_20260823T040000Z/snp_core15_inputs.parquet"
    proxy_path = RESEARCH / "data/processed/credit_proxy_only_impact/credit_proxy_only_phase1_20260902T001000Z/proxy_only_credit_inputs.parquet"
    metadata_path = RESEARCH / "data/processed/signal_bank/sp3_core15_signal_bank_20260823T041000Z/sp3_candidate_metadata.parquet"
    material_path = RESEARCH / "outputs/snp/combo2/material_input/proxy_only_combo1_material_band_balanced_20260904T043000Z/combo2_material_input.parquet"

    required_indices = sorted({index for item in contract["final_combo2"] for index in item["material_indices"]})
    material = pd.read_parquet(material_path).set_index("material_index", verify_integrity=True).loc[required_indices].reset_index()
    expected = {index: child for item in contract["final_combo2"] for index, child in zip(item["material_indices"], item["child_combo1_ids"], strict=True)}
    if any(str(row.material_combo1_id) != expected[int(row.material_index)] for row in material.itertuples(index=False)):
        raise RuntimeError("Final Combo2 child mapping differs from the frozen contract")

    legacy = pd.read_parquet(panel_path)
    legacy["date"] = pd.to_datetime(legacy["date"]).dt.normalize()
    proxy = pd.read_parquet(proxy_path)
    proxy["date"] = pd.to_datetime(proxy["date"]).dt.normalize()
    panel = legacy[["date", "open", "high", "low", "close", "performance_calendar_eligible", "ohlc_signal_eligible", "real_yield_10y", "real_yield_10y_available_date", "spread_10y2y", "spread_10y2y_available_date", "spread_10y3m", "spread_10y3m_available_date", "dgs10", "dgs10_available_date", "vix3m", "vix_spread_safe", "vix_spread_source_date", "equal_weight_price", "breadth_raw", "breadth_source_date"]].copy()
    panel = panel.merge(proxy, on="date", how="left", validate="one_to_one")
    panel = panel.rename(columns={
        "hy_safe_proxy_only": "hy_oas_safe", "ig_safe_proxy_only": "ig_oas_safe",
        "global_credit_stress_safe_proxy_only": "global_credit_stress_safe",
        "real_yield_10y_available_date": "real_yield_10y_source_observation_date",
        "spread_10y2y_available_date": "spread_10y2y_source_observation_date",
        "spread_10y3m_available_date": "spread_10y3m_source_observation_date",
        "dgs10_available_date": "dgs10_source_observation_date",
        "hy_available_date": "hy_source_observation_date", "ig_available_date": "ig_source_observation_date",
        "nfci_available_date": "nfci_source_observation_date", "vix_available_date": "vix_source_observation_date",
    })
    panel["spx_performance_return"] = pd.to_numeric(panel["close"], errors="coerce").pct_change()
    panel["breadth_input_eligible"] = panel["equal_weight_price"].gt(0) & panel["close"].gt(0)
    panel["core15_input_eligible"] = panel[["ohlc_signal_eligible", "breadth_input_eligible"]].all(axis=1)
    panel["core15_input_eligible"] &= panel[["hy_oas_safe", "ig_oas_safe", "global_credit_stress_safe", "vix", "vix3m", "real_yield_10y", "spread_10y2y", "spread_10y3m", "dgs10"]].notna().all(axis=1)
    panel = panel.sort_values("date", kind="mergesort").reset_index(drop=True)

    core_ids = _selected_core_ids(contract, material)
    metadata = pd.read_parquet(metadata_path)
    registry = metadata.loc[metadata["candidate_id"].isin(core_ids)].copy()
    if len(registry) != len(core_ids) or registry["candidate_id"].duplicated().any():
        raise RuntimeError("Selected Core15 registry cannot be resolved exactly")
    source_by_indicator = {
        "global_credit_stress": ("global_credit_stress_safe", "identity"), "snp_bollinger": ("close", "identity"),
        "snp_breadth": ("breadth_raw", "identity"), "snp_hv": ("close", "identity"),
        "snp_index_level": ("close", "identity"), "snp_natr": ("close", "identity"),
        "snp_rsi": ("close", "identity"), "us_10y_2y_spread": ("spread_10y2y", "identity"),
        "us_10y_3m_spread": ("spread_10y3m", "identity"), "us_10y_nominal_yield_slope": ("dgs10", "identity"),
        "us_10y_real_yield": ("real_yield_10y", "negate"), "us_hy_oas": ("hy_oas_safe", "identity"),
        "us_ig_oas": ("ig_oas_safe", "identity"), "vix_level": ("vix", "negate"), "vix_spread": ("vix_spread_safe", "identity"),
    }
    registry["source_column"] = registry["indicator_id"].map(lambda value: source_by_indicator[str(value)][0])
    registry["transform"] = registry["indicator_id"].map(lambda value: source_by_indicator[str(value)][1])
    registry = registry.sort_values("candidate_id", kind="mergesort").reset_index(drop=True)

    final1 = pd.DataFrame(contract["final_combo1"])
    final1["family"] = "Combo1"
    final1["selection_type"] = final1["research_lane"]
    final1["component_ids_key"] = final1["component_ids"].map("|".join)
    final1["display_order"] = range(1, len(final1) + 1)
    final1["n_or_m"] = final1["n"]
    final2 = pd.DataFrame(contract["final_combo2"])
    final2["family"] = "Combo2"
    final2["selection_type"] = final2["research_lane"]
    final2["component_ids_key"] = ""
    final2["display_order"] = range(1, len(final2) + 1)
    final2["n_or_m"] = final2["m"]
    final10 = pd.concat([final1, final2], ignore_index=True, sort=False)

    child_rows: list[dict[str, object]] = []
    material_by_id = material.set_index("material_combo1_id", verify_integrity=True)
    for parent in final2.itertuples(index=False):
        for order, child_id in enumerate(parent.child_combo1_ids, start=1):
            child = material_by_id.loc[str(child_id)]
            child_rows.append({
                "parent_candidate_id": parent.candidate_id, "child_order": order,
                "child_canonical_parent_id": str(child_id), "child_n": int(child.n), "child_K": int(child.K), "child_L": int(child.L),
                "child_component_ids_key": str(child.candidate_ids_key),
            })
    children = pd.DataFrame(child_rows).sort_values(["parent_candidate_id", "child_order"], kind="mergesort")

    records: dict[str, dict[str, object]] = {}
    _write(panel, FROZEN / "frozen_spx_proxy_only_core15_input.parquet", records)
    _write(registry, FROZEN / "core15_selected_candidate_registry.parquet", records)
    final_path = ASSETS / "spx_macro9_final10_runtime.csv"
    if final_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing asset: {final_path}")
    final10.to_csv(final_path, index=False)
    records[str(final_path.relative_to(ASSETS))] = {"sha256": sha256(final_path), "rows": int(len(final10)), "columns": list(final10.columns)}
    child_path = ASSETS / "spx_macro9_combo2_child_mapping.csv"
    if child_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing asset: {child_path}")
    children.to_csv(child_path, index=False)
    records[str(child_path.relative_to(ASSETS))] = {"sha256": sha256(child_path), "rows": int(len(children)), "columns": list(children.columns)}

    manifest = {
        "status": "PASS_SPX_MACRO9_STAGE3_LIVE_INPUT_ASSETS_READY", "runtime_dependency": "DASHBOARD_OWNED_ASSETS_ONLY",
        "source_contract": {"proxy_only": True, "direct_oas_or_stitching": "FORBIDDEN", "spread_series": ["T10Y2Y", "T10Y3M"], "vix3m_recent_source": "CBOE_VIX3M_NATIVE"},
        "provenance": {"legacy_non_credit_panel": {"path": str(panel_path.relative_to(RESEARCH)), "sha256": sha256(panel_path)}, "proxy_credit_panel": {"path": str(proxy_path.relative_to(RESEARCH)), "sha256": sha256(proxy_path)}, "candidate_metadata": {"path": str(metadata_path.relative_to(RESEARCH)), "sha256": sha256(metadata_path)}, "material_children": {"path": str(material_path.relative_to(RESEARCH)), "sha256": sha256(material_path)}},
        "outputs": records,
    }
    manifest_path = FROZEN / "spx_macro9_live_asset_manifest.json"
    if manifest_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing asset: {manifest_path}")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
