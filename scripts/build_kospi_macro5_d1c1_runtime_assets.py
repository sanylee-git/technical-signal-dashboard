from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kospi_macro5_runtime.engine import (  # noqa: E402
    D1C1Context,
    build_dependency_graph,
    read_json,
    sha256_file,
    write_json,
)


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KOSPI_ROOT = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kospi")
KOSPI_ROOT = Path(os.environ.get("KOSPI_MACRO_ROOT", DEFAULT_KOSPI_ROOT))


def output_value(manifest: dict, key: str) -> str:
    value = (manifest.get("output_files") or manifest.get("outputs") or {})[key]
    if isinstance(value, dict):
        return str(value["path"])
    return str(value)


def main() -> None:
    ctx = D1C1Context(DASHBOARD_ROOT, KOSPI_ROOT)
    ctx.asset_dir.mkdir(exist_ok=True)
    ctx.report_dir.mkdir(exist_ok=True)

    graph = build_dependency_graph(ctx)
    graph_path = ctx.asset_dir / "kospi_d1c1_dependency_graph.json"
    write_json(graph_path, graph)

    stage3c = read_json(KOSPI_ROOT / "manifests/stage3c_extended_latest_signal_bank.json")
    candidate_meta_path = KOSPI_ROOT / output_value(stage3c, "candidate_metadata_parquet")
    candidate_meta = pd.read_parquet(candidate_meta_path)
    required_meta = candidate_meta[
        candidate_meta["candidate_id"].isin(graph["required_core15_components"])
    ].copy()
    if len(required_meta) != graph["required_core15_component_count"]:
        missing = sorted(set(graph["required_core15_components"]) - set(required_meta["candidate_id"]))
        raise RuntimeError(f"required Core15 metadata missing: {missing[:5]}")

    meta_path = ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet"
    meta_csv_path = ctx.asset_dir / "kospi_d1c1_required_core15_metadata.csv"
    required_meta.to_parquet(meta_path, index=False)
    required_meta.to_csv(meta_csv_path, index=False)

    source = None
    missing_components: list[str] = []
    required_meta["_matrix_id"] = required_meta["source_series_id"].where(
        required_meta["source_series_id"].notna(),
        required_meta["indicator_id"],
    )
    for matrix_id, family_meta in required_meta.groupby("_matrix_id"):
        signal_path = (
            KOSPI_ROOT
            / "outputs/kospi/run_20260731T005207Z_stage03c_core15_extended_signal_bank_v1"
            / "03c_core15_extended_signal_bank/signals_by_indicator"
            / f"{matrix_id}_risk_state.parquet"
        )
        if not signal_path.exists():
            raise FileNotFoundError(f"risk state matrix missing: {signal_path}")
        needed = ["date", *family_meta["candidate_id"].tolist()]
        table = pd.read_parquet(signal_path)
        cols = [col for col in needed if col in table.columns]
        missing_components.extend([col for col in needed if col not in table.columns and col != "date"])
        one = table[cols].copy()
        source = one if source is None else source.merge(one, on="date", how="outer")

    if missing_components:
        raise RuntimeError(f"Core15 risk state columns missing: {missing_components[:5]}")

    source["date"] = pd.to_datetime(source["date"]).dt.strftime("%Y-%m-%d")
    source = source.sort_values("date").reset_index(drop=True)

    # Combo2 official input is the child Combo1 raw risk_state bank produced
    # by Stage06A, not child Combo1 T+1 and not a fresh full-history
    # recomputation with a different initial state convention.
    stage6a = read_json(KOSPI_ROOT / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json")
    raw_dict = pd.read_csv(KOSPI_ROOT / stage6a["output_files"]["raw_state_dictionary"]).reset_index(drop=True)
    raw_bank = pd.read_parquet(KOSPI_ROOT / stage6a["output_files"]["raw_state_bank"])
    raw_bank["date"] = pd.to_datetime(raw_bank["date"]).dt.strftime("%Y-%m-%d")
    child_map = {}
    for child_id in graph["required_child_combo1"]:
        matches = raw_dict.index[raw_dict["combo1_id"].astype(str) == child_id].tolist()
        if len(matches) != 1:
            raise RuntimeError(f"required child raw state not found once: {child_id}")
        child_map[child_id] = f"c{matches[0] + 1:02d}"
    child_source = raw_bank[["date", *child_map.values()]].rename(
        columns={v: k for k, v in child_map.items()}
    )
    source = source.merge(child_source, on="date", how="outer").sort_values("date").reset_index(drop=True)
    source_path = ctx.asset_dir / "kospi_d1c1_frozen_core15_source_base.parquet"
    source.to_parquet(source_path, index=False)

    contract = {
        "gate": "PASS_KOSPI_MACRO5_D1C1_RUNTIME_CONTRACT_READY"
        if graph["dependency_missing_count"] == 0
        else "BLOCKED_KOSPI_MACRO5_D1C1_RUNTIME_DEPENDENCY_MISSING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_stage": "D1-C1_RUNTIME_CONTRACT_AND_FROZEN_SOURCE_BASE",
        "official_operating_model": False,
        "dashboard_applied": False,
        "shadow_mode": True,
        "signal_semantics": {
            "core15_component": "RAW_RISK_STATE",
            "combo1": "RAW_RISK_STATE_FROM_CORE15_COMPONENTS",
            "combo2_input": "CHILD_COMBO1_RAW_RISK_STATE",
            "combo2_child_t1_forbidden": True,
            "final_t1_applied_once": True,
            "missing_as_risk_on_forbidden": True,
        },
        "frozen_replay_required_gate": "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY",
        "c1b_requires_c1a_pass": True,
        "source_base": {
            "path": ctx.rel_dashboard(source_path),
            "sha256": sha256_file(source_path),
            "rows": int(len(source)),
            "date_start": source["date"].min(),
            "date_end": source["date"].max(),
            "component_columns": int(source.shape[1] - 1),
            "core15_component_columns": graph["required_core15_component_count"],
            "child_combo1_raw_state_columns": graph["required_child_combo1_count"],
        },
        "required_core15_metadata": {
            "path": ctx.rel_dashboard(meta_path),
            "sha256": sha256_file(meta_path),
            "csv_path": ctx.rel_dashboard(meta_csv_path),
            "csv_sha256": sha256_file(meta_csv_path),
            "rows": int(len(required_meta)),
        },
        "dependency_graph": {
            "path": ctx.rel_dashboard(graph_path),
            "sha256": sha256_file(graph_path),
            "required_core15_component_count": graph["required_core15_component_count"],
            "required_child_combo1_count": graph["required_child_combo1_count"],
            "dependency_missing_count": graph["dependency_missing_count"],
        },
        "source_manifests": {
            "stage3c": {
                "path": "macro_dashboard_kospi/manifests/stage3c_extended_latest_signal_bank.json",
                "sha256": sha256_file(KOSPI_ROOT / "manifests/stage3c_extended_latest_signal_bank.json"),
            },
            "stage6a": {
                "path": "macro_dashboard_kospi/manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json",
                "sha256": sha256_file(KOSPI_ROOT / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json"),
            },
            "stage7c2": {
                "path": "macro_dashboard_kospi/manifests/stage7c2_latest_combo2_union58_decision10_proposal.json",
                "sha256": sha256_file(KOSPI_ROOT / "manifests/stage7c2_latest_combo2_union58_decision10_proposal.json"),
            },
        },
    }
    contract_path = ctx.asset_dir / "kospi_d1c1_runtime_contract.json"
    write_json(contract_path, contract)

    coverage = required_meta[
        ["candidate_id", "indicator_id", "kind", "source_column", "source_series_id", "param_id", "valid_start", "valid_end"]
    ].copy()
    coverage_path = ctx.report_dir / "kospi_macro5_d1c1_contract_coverage.csv"
    coverage.to_csv(coverage_path, index=False)

    report = f"""# KOSPI Macro5 D1-C1 Runtime Contract

Gate: `{contract['gate']}`

- Required Core15 components: {graph['required_core15_component_count']}
- Required child Combo1 raw states: {graph['required_child_combo1_count']}
- Frozen source-base rows: {len(source)}
- Frozen source-base period: {source['date'].min()} ~ {source['date'].max()}
- Missing dependencies: {graph['dependency_missing_count']}

Signal semantics:

- Combo2 input is child Combo1 raw risk_state.
- Child Combo1 T+1 is forbidden for Combo2.
- Final9 T+1 is applied once only.
- Missing signal values are not interpreted as Risk-on.
"""
    report_path = ctx.report_dir / "kospi_macro5_d1c1_preflight.md"
    report_path.write_text(report)

    print(json.dumps({"gate": contract["gate"], "source_rows": len(source)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
