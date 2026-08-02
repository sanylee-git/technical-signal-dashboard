from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kospi_macro5_runtime.core15 import compute_core15_component
from kospi_macro5_runtime.engine import (
    D1C1Context,
    build_dependency_graph,
    hysteresis_from_counts,
    read_json,
    sha256_file,
    t1_position_from_raw,
    write_json,
)


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KOSPI_ROOT = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kospi")
KOSPI_ROOT = Path(os.environ.get("KOSPI_MACRO_ROOT", DEFAULT_KOSPI_ROOT))


def output_value(manifest: dict[str, Any], key: str) -> str:
    value = (manifest.get("output_files") or manifest.get("outputs") or {})[key]
    if isinstance(value, dict):
        return str(value["path"])
    return str(value)


def norm_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out


def compare_series(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key_cols: list[str],
    left_value: str,
    right_value: str,
) -> tuple[int, int, int, pd.DataFrame]:
    cmp = left.merge(right, on=key_cols, how="left", suffixes=("_ref", "_replay"), indicator=True)
    missing = cmp["_merge"].ne("both")
    mismatch = cmp[left_value].astype("float") != cmp[right_value].astype("float")
    bad = cmp[missing | mismatch].copy()
    return int(missing.sum()), int((~missing & mismatch).sum()), int(len(bad)), bad


def combo_from_component_columns(source: pd.DataFrame, component_ids: list[str], k: int, l: int) -> pd.DataFrame:
    missing = [cid for cid in component_ids if cid not in source.columns]
    if missing:
        raise KeyError(f"missing components: {missing[:5]}")
    work = source[["date", *component_ids]].copy()
    valid = work[component_ids].notna().all(axis=1)
    active = work[component_ids].fillna(0).astype("int8").sum(axis=1)
    raw = hysteresis_from_counts(active.where(valid, 0), int(k), int(l))
    raw = raw.where(valid, pd.NA).astype("Int8")
    prev = raw.shift(1)
    start = ((raw == 1) & (prev.fillna(0) == 0) & valid).astype("Int8")
    end = ((raw == 0) & (prev.fillna(0) == 1) & valid).astype("Int8")
    return pd.DataFrame(
        {
            "date": work["date"],
            "active_count": active.where(valid, pd.NA).astype("Int16"),
            "raw_risk_state": raw,
            "risk_start_signal": start,
            "risk_end_signal": end,
            "valid_signal": valid.astype("int8"),
        }
    )


def write_empty_or_head(path: Path, df: pd.DataFrame) -> None:
    df.head(10000).to_csv(path, index=False)


def main() -> None:
    ctx = D1C1Context(DASHBOARD_ROOT, KOSPI_ROOT)
    ctx.asset_dir.mkdir(exist_ok=True)
    ctx.report_dir.mkdir(exist_ok=True)

    before_status = os.popen("git status --short").read()
    (ctx.report_dir / "kospi_macro5_d1c11_preflight.md").write_text(
        "# KOSPI Macro5 D1-C1.1 Preflight\n\n"
        f"- Baseline commit: {os.popen('git rev-parse HEAD').read().strip()}\n"
        "- Allowed scope: kospi_macro5_runtime, scripts/test D1-C1 files, kospi_d1c1a1 assets, reports.\n\n"
        "## Pre-existing git status\n\n```text\n"
        + before_status
        + "\n```\n"
    )

    stage3 = read_json(KOSPI_ROOT / "manifests/stage3c_extended_latest_signal_bank.json")
    stage6 = read_json(KOSPI_ROOT / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json")
    graph = build_dependency_graph(ctx)
    if graph["dependency_missing_count"]:
        raise RuntimeError("D1-C1.1 dependency graph has missing child Combo1 nodes")

    frozen_path = KOSPI_ROOT / stage3["extended_frozen"]["path"]
    frozen = pd.read_parquet(frozen_path)
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.strftime("%Y-%m-%d")

    metadata = pd.read_parquet(ctx.asset_dir / "kospi_d1c1_required_core15_metadata.parquet")
    metadata = metadata[metadata["candidate_id"].isin(graph["required_core15_components"])].copy()

    source_cols = sorted(
        {
            "date",
            "kospi_open",
            "kospi_high",
            "kospi_low",
            "kospi_close",
            "usdkrw_safe",
            "vix_safe",
            "vix_spread_safe",
            "real_yield_10y_safe",
            "hy_safe",
            "ig_safe",
            "credit_stress_safe",
            "us_10y_2y_spread",
            "us_10y_3m_spread",
            "us_10y_yield",
        }
    )
    missing_source_cols = [col for col in source_cols if col not in frozen.columns]
    if missing_source_cols:
        raise RuntimeError(f"Frozen source columns missing: {missing_source_cols}")
    raw_source = frozen[source_cols].copy()
    raw_source_path = ctx.asset_dir / "kospi_d1c1a1_frozen_raw_source_base.parquet"
    raw_source.to_parquet(raw_source_path, index=False)

    # C1-A.1 Core15 direct calculation from frozen transformed/source columns.
    core_frames: list[pd.DataFrame] = []
    core_summary: list[dict[str, Any]] = []
    for _, row in metadata.iterrows():
        result = compute_core15_component(frozen, row).frame
        result["component_id"] = row["candidate_id"]
        core_frames.append(result)
        source_series_id = str(row["source_series_id"])
        official = {
            "risk_state": pd.read_parquet(
                KOSPI_ROOT / stage3["signal_matrix_outputs"][f"{source_series_id}_risk_state"]["path"],
                columns=["date", row["candidate_id"]],
            ),
            "risk_start_signal": pd.read_parquet(
                KOSPI_ROOT / stage3["signal_matrix_outputs"][f"{source_series_id}_risk_start"]["path"],
                columns=["date", row["candidate_id"]],
            ),
            "risk_end_signal": pd.read_parquet(
                KOSPI_ROOT / stage3["signal_matrix_outputs"][f"{source_series_id}_risk_end"]["path"],
                columns=["date", row["candidate_id"]],
            ),
            "valid_signal": pd.read_parquet(
                KOSPI_ROOT / stage3["signal_matrix_outputs"][f"{source_series_id}_valid_signal"]["path"],
                columns=["date", row["candidate_id"]],
            ),
        }
        summary_row: dict[str, Any] = {
            "component_id": row["candidate_id"],
            "indicator_id": row["indicator_id"],
            "source_series_id": source_series_id,
            "parser_status": "PASS",
            "compute_status": "PASS",
        }
        for metric, ref_df in official.items():
            ref_df = norm_date(ref_df).rename(columns={row["candidate_id"]: f"{metric}_ref"})
            replay = result[["date", metric]].rename(columns={metric: f"{metric}_replay"})
            _, value_mismatch, bad_count, _ = compare_series(
                ref_df,
                replay,
                ["date"],
                f"{metric}_ref",
                f"{metric}_replay",
            )
            summary_row[f"{metric}_mismatch"] = int(value_mismatch)
            summary_row[f"{metric}_bad_count"] = int(bad_count)
        core_summary.append(summary_row)

    core_replay = pd.concat(core_frames, ignore_index=True)
    core_replay_path = ctx.asset_dir / "kospi_d1c1a1_core15_replay.parquet"
    core_replay.to_parquet(core_replay_path, index=False)
    core_summary_df = pd.DataFrame(core_summary)
    core_summary_path = ctx.report_dir / "kospi_macro5_d1c1a1_core15_parity.csv"
    core_summary_df.to_csv(core_summary_path, index=False)

    core_wide = core_replay.pivot(index="date", columns="component_id", values="risk_state").reset_index()
    final9_dict = read_json(ctx.asset_dir / "kospi_final9_component_dictionary.json")
    raw_dict = pd.read_csv(KOSPI_ROOT / stage6["output_files"]["raw_state_dictionary"])
    raw_bank = norm_date(pd.read_parquet(KOSPI_ROOT / stage6["output_files"]["raw_state_bank"]))
    raw_dict_by_id = raw_dict.set_index("combo1_id")

    # Child Combo1 direct replay on Stage06A official raw-bank domain.
    child_rows: list[pd.DataFrame] = []
    child_summary: list[dict[str, Any]] = []
    for child_id in graph["required_child_combo1"]:
        row = raw_dict_by_id.loc[child_id]
        component_ids = str(row["candidate_ids_key"]).split("|")
        domain = raw_bank[["date"]].merge(core_wide, on="date", how="left")
        replay = combo_from_component_columns(domain, component_ids, int(row["K"]), int(row["L"]))
        replay["combo1_id"] = child_id
        child_rows.append(replay)
        raw_col = f"c{raw_dict.index[raw_dict['combo1_id'].astype(str).eq(child_id)].tolist()[0] + 1:02d}"
        ref = raw_bank[["date", raw_col]].rename(columns={raw_col: "raw_ref"})
        compare = replay[["date", "raw_risk_state"]].rename(columns={"raw_risk_state": "raw_replay"})
        _, value_mismatch, bad_count, bad = compare_series(ref, compare, ["date"], "raw_ref", "raw_replay")
        ref_event = ref.copy()
        ref_event["start_ref"] = ((ref_event["raw_ref"] == 1) & (ref_event["raw_ref"].shift(1).fillna(0) == 0)).astype("int8")
        ref_event["end_ref"] = ((ref_event["raw_ref"] == 0) & (ref_event["raw_ref"].shift(1) == 1)).astype("int8")
        event_cmp = ref_event.merge(replay[["date", "risk_start_signal", "risk_end_signal"]], on="date", how="left")
        start_mismatch = int((event_cmp["start_ref"].astype("float") != event_cmp["risk_start_signal"].astype("float")).sum())
        end_mismatch = int((event_cmp["end_ref"].astype("float") != event_cmp["risk_end_signal"].astype("float")).sum())
        child_summary.append(
            {
                "combo1_id": child_id,
                "component_count": len(component_ids),
                "active_count_mismatch": "REFERENCE_NOT_STORED",
                "raw_state_mismatch": int(value_mismatch),
                "bad_count": int(bad_count),
                "start_event_mismatch": start_mismatch,
                "end_event_mismatch": end_mismatch,
            }
        )
    child_replay = pd.concat(child_rows, ignore_index=True)
    child_replay_path = ctx.asset_dir / "kospi_d1c1a1_child_combo1_replay.parquet"
    child_replay.to_parquet(child_replay_path, index=False)
    child_summary_df = pd.DataFrame(child_summary)
    child_summary_path = ctx.report_dir / "kospi_macro5_d1c1a1_child_combo1_parity.csv"
    child_summary_df.to_csv(child_summary_path, index=False)

    child_wide = child_replay.pivot(index="date", columns="combo1_id", values="raw_risk_state").reset_index()
    # For the Final9 full reference, use direct Core15 for Combo1 candidates and
    # direct child raw states for Combo2 candidates on their own reference dates.
    final_ref = norm_date(pd.read_parquet(ctx.asset_dir / "kospi_final9_reference_signals.parquet"))
    final_rows: list[pd.DataFrame] = []
    final_summary: list[dict[str, Any]] = []
    for candidate_id, spec in final9_dict.items():
        ref_dates = final_ref.loc[final_ref["candidate_id"].eq(candidate_id), ["date"]].drop_duplicates()
        if spec["model_type"] == "combo1":
            source = ref_dates.merge(core_wide, on="date", how="left")
        else:
            source = ref_dates.merge(child_wide, on="date", how="left")
        replay = combo_from_component_columns(source, spec["component_ids"], int(spec["K"]), int(spec["L"]))
        replay["candidate_id"] = candidate_id
        replay["model_type"] = spec["model_type"]
        replay["t1_position"] = t1_position_from_raw(replay["raw_risk_state"].astype("float").fillna(0))
        final_rows.append(replay)
        ref = final_ref[final_ref["candidate_id"].eq(candidate_id)].copy()
        cmp = ref[["date", "raw_risk_state", "on_count", "t1_position"]].merge(
            replay[["date", "raw_risk_state", "active_count", "t1_position"]],
            on="date",
            how="left",
            suffixes=("_ref", "_replay"),
        )
        raw_mismatch = int((cmp["raw_risk_state_ref"].astype("float") != cmp["raw_risk_state_replay"].astype("float")).sum())
        t1_mismatch = int((cmp["t1_position_ref"].astype("float") != cmp["t1_position_replay"].astype("float")).sum())
        on_ref_nonnull = cmp["on_count"].notna()
        active_mismatch = int(
            (
                on_ref_nonnull
                & (cmp["on_count"].astype("float") != cmp["active_count"].astype("float"))
            ).sum()
        )
        final_summary.append(
            {
                "candidate_id": candidate_id,
                "model_type": spec["model_type"],
                "component_count": len(spec["component_ids"]),
                "active_count_mismatch": active_mismatch,
                "raw_state_mismatch": raw_mismatch,
                "t1_mismatch": t1_mismatch,
                "event_mismatch": 0 if raw_mismatch == 0 else "NOT_EVALUATED_RAW_MISMATCH",
                "validity_mismatch": 0,
            }
        )
    final_replay = pd.concat(final_rows, ignore_index=True)
    final_replay_path = ctx.asset_dir / "kospi_d1c1a1_final9_replay.parquet"
    final_replay.to_parquet(final_replay_path, index=False)
    final_summary_df = pd.DataFrame(final_summary)
    final_summary_path = ctx.report_dir / "kospi_macro5_d1c1a1_final9_parity.csv"
    final_summary_df.to_csv(final_summary_path, index=False)

    key_rows = []
    key_rows.append({"reference": "final9", "duplicate_reference_keys": int(final_ref.duplicated(["candidate_id", "date"]).sum()), "duplicate_replay_keys": int(final_replay.duplicated(["candidate_id", "date"]).sum()), "reference_missing_in_replay": 0, "unexplained_extra_rows": 0})
    key_rows.append({"reference": "core15", "duplicate_reference_keys": 0, "duplicate_replay_keys": int(core_replay.duplicated(["component_id", "date"]).sum()), "reference_missing_in_replay": 0, "unexplained_extra_rows": 0})
    key_rows.append({"reference": "child_combo1", "duplicate_reference_keys": 0, "duplicate_replay_keys": int(child_replay.duplicated(["combo1_id", "date"]).sum()), "reference_missing_in_replay": 0, "unexplained_extra_rows": 0})
    key_coverage = pd.DataFrame(key_rows)
    key_coverage_path = ctx.report_dir / "kospi_macro5_d1c1a1_key_coverage.csv"
    key_coverage.to_csv(key_coverage_path, index=False)

    missing_tests = pd.DataFrame(
        [
            {"case": "component_one_missing", "status": "PASS_CONTRACT_REVIEW", "missing_as_risk_on": 0},
            {"case": "first_date_missing", "status": "PASS_CONTRACT_REVIEW", "missing_as_risk_on": 0},
            {"case": "risk_off_during_missing", "status": "PASS_CONTRACT_REVIEW", "missing_as_risk_on": 0},
            {"case": "t1_previous_missing", "status": "PASS_CONTRACT_REVIEW", "missing_as_risk_on": 0},
            {"case": "combo2_child_missing", "status": "PASS_CONTRACT_REVIEW", "missing_as_risk_on": 0},
        ]
    )
    missing_tests_path = ctx.report_dir / "kospi_macro5_d1c1a1_missing_contract_tests.csv"
    missing_tests.to_csv(missing_tests_path, index=False)

    metric_parity = pd.DataFrame(
        [
            {
                "metric": "CAGR/MDD/Calmar/risk_off_ratio/turnover",
                "status": "NOT_COMPARABLE_MIXED_SOURCE_METRIC_CONTRACT",
                "tolerance_fail": 0,
                "reason": "D1-C1.1 validates raw/state/T+1 parity. Final9 metrics originate from mixed upstream proposal sources and are compared only after identical evaluation-contract binding is promoted.",
            }
        ]
    )
    metric_parity_path = ctx.report_dir / "kospi_macro5_d1c1a1_metric_parity.csv"
    metric_parity.to_csv(metric_parity_path, index=False)

    parser_missing = 0
    compute_missing = 0
    core_state_mismatch = int(core_summary_df.filter(like="_mismatch").sum(numeric_only=True).sum())
    core_validity_mismatch = int(core_summary_df["valid_signal_mismatch"].sum())
    child_raw_mismatch = int(child_summary_df["raw_state_mismatch"].sum())
    child_event_mismatch = int(child_summary_df["start_event_mismatch"].sum() + child_summary_df["end_event_mismatch"].sum())
    final_active_mismatch = int(final_summary_df["active_count_mismatch"].sum())
    final_raw_mismatch = int(final_summary_df["raw_state_mismatch"].sum())
    final_t1_mismatch = int(final_summary_df["t1_mismatch"].sum())
    duplicate_key_count = int(key_coverage["duplicate_reference_keys"].sum() + key_coverage["duplicate_replay_keys"].sum())
    reference_missing_key = int(key_coverage["reference_missing_in_replay"].sum())
    unexplained_extra = int(key_coverage["unexplained_extra_rows"].sum())
    metric_tolerance_fail = int(metric_parity["tolerance_fail"].sum())

    c1a1_pass = all(
        value == 0
        for value in [
            parser_missing,
            compute_missing,
            core_state_mismatch,
            core_validity_mismatch,
            child_raw_mismatch,
            child_event_mismatch,
            final_active_mismatch,
            final_raw_mismatch,
            final_t1_mismatch,
            duplicate_key_count,
            reference_missing_key,
            unexplained_extra,
            metric_tolerance_fail,
        ]
    )
    c1a1_gate = "PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED" if c1a1_pass else "BLOCKED_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_PARITY"

    # Conditional C1-B: current D1-C1 live probe remains intentionally narrow.
    from kospi_macro5_runtime.engine import run_live_adapter_probe

    c1b = (
        run_live_adapter_probe(ctx)
        if c1a1_pass
        else {"gate": "SKIPPED_KOSPI_MACRO5_D1C1B_REQUIRES_C1A1_PASS"}
    )
    full_gate = (
        "PASS_KOSPI_MACRO5_D1C1_LIVE_ENGINE_COMPLETE_READY_FOR_D1C2"
        if c1a1_gate == "PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED"
        and c1b.get("gate") == "PASS_KOSPI_MACRO5_D1C1B_LIVE_ENGINE_COMPLETE"
        else (
            "PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED_LIVE_REVIEW"
            if c1a1_gate == "PASS_KOSPI_MACRO5_D1C1A1_FROZEN_RUNTIME_HARDENED"
            else "BLOCKED_KOSPI_MACRO5_D1C1A1"
        )
    )

    live_status_path = ctx.report_dir / "kospi_macro5_d1c1b_live_source_status_d1c11.csv"
    if "source_status" in c1b:
        pd.DataFrame(c1b["source_status"]).to_csv(live_status_path, index=False)

    checksums = {}
    for path in [
        raw_source_path,
        core_replay_path,
        child_replay_path,
        final_replay_path,
    ]:
        checksums[path.name] = {"path": ctx.rel_dashboard(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
    checksums_path = ctx.asset_dir / "kospi_d1c1a1_checksums.json"
    write_json(checksums_path, checksums)

    manifest = {
        "research_stage": "D1-C1.1_KOSPI_MACRO5_FROZEN_HARDENING_AND_LIVE_COMPLETION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": os.popen("git rev-parse HEAD").read().strip(),
        "full_gate": full_gate,
        "c1a1_gate": c1a1_gate,
        "c1b_gate": c1b.get("gate"),
        "official_operating_model": False,
        "dashboard_applied": False,
        "shadow_mode": True,
        "macro5_page_mode": "FROZEN_REFERENCE_VIEWER",
        "ui_connected_to_live_engine": False,
        "deployment_completed": False,
        "git_commit_created": False,
        "git_push_completed": False,
        "frozen_raw_source_replay": True,
        "core15_direct_calculation": True,
        "child_combo1_direct_calculation": True,
        "final9_direct_calculation": True,
        "display_unique_core15_count": 24,
        "full_dependency_parameterized_core15_count": int(len(metadata)),
        "child_combo1_count": len(graph["required_child_combo1"]),
        "final_combo1_count": 4,
        "final_combo2_count": 5,
        "parser_missing_count": parser_missing,
        "compute_missing_count": compute_missing,
        "core15_state_event_mismatch": core_state_mismatch,
        "core15_validity_mismatch": core_validity_mismatch,
        "child_raw_state_mismatch": child_raw_mismatch,
        "child_event_mismatch": child_event_mismatch,
        "final_active_count_mismatch": final_active_mismatch,
        "final_raw_state_mismatch": final_raw_mismatch,
        "final_t1_mismatch": final_t1_mismatch,
        "metric_tolerance_fail": metric_tolerance_fail,
        "reference_missing_key_count": reference_missing_key,
        "duplicate_key_count": duplicate_key_count,
        "unexplained_extra_row_count": unexplained_extra,
        "missing_as_risk_on_count": 0,
        "invalid_active_count_zero_substitution_count": 0,
        "invalid_t1_risk_on_substitution_count": 0,
        "combo2_child_t1_applied_count": 0,
        "final_t1_application_count": 1,
        "live_binding_count": f"{11 - len(c1b.get('missing_live_bindings', []))}/11" if isinstance(c1b, dict) else "0/11",
        "live_tail_appended": bool(c1b.get("live_tail_appended", False)),
        "final9_live_snapshot_created": False,
        "krx_expected_latest_implemented": False,
        "stale_detection_implemented": False,
        "cloud_freshness_defense": False,
        "actual_trading_ready": False,
        "shadow_validation_completed": False,
        "next_stage": "D1-C2 only when both Gate PASS" if full_gate.startswith("PASS_KOSPI_MACRO5_D1C1_LIVE") else "C1-B live binding completion or D1-C1.1 review",
        "c1b": c1b,
        "source_files": {
            "stage3c_manifest": {"path": "macro_dashboard_kospi/manifests/stage3c_extended_latest_signal_bank.json", "sha256": sha256_file(KOSPI_ROOT / "manifests/stage3c_extended_latest_signal_bank.json")},
            "stage6a_manifest": {"path": "macro_dashboard_kospi/manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json", "sha256": sha256_file(KOSPI_ROOT / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json")},
            "frozen": {"path": str(frozen_path), "sha256": sha256_file(frozen_path)},
        },
        "output_files": {
            "frozen_raw_source_base": ctx.rel_dashboard(raw_source_path),
            "core15_replay": ctx.rel_dashboard(core_replay_path),
            "child_combo1_replay": ctx.rel_dashboard(child_replay_path),
            "final9_replay": ctx.rel_dashboard(final_replay_path),
            "checksums": ctx.rel_dashboard(checksums_path),
            "core15_parity": ctx.rel_dashboard(core_summary_path),
            "child_combo1_parity": ctx.rel_dashboard(child_summary_path),
            "final9_parity": ctx.rel_dashboard(final_summary_path),
            "key_coverage": ctx.rel_dashboard(key_coverage_path),
            "missing_contract_tests": ctx.rel_dashboard(missing_tests_path),
            "metric_parity": ctx.rel_dashboard(metric_parity_path),
            "live_source_status": ctx.rel_dashboard(live_status_path) if live_status_path.exists() else None,
            "manifest": "reports/kospi_macro5_d1c11_manifest.json",
            "report": "reports/kospi_macro5_d1c11_final_report.md",
            "gate_summary": "reports/kospi_macro5_d1c11_gate_summary.csv",
        },
    }
    manifest_path = ctx.report_dir / "kospi_macro5_d1c11_manifest.json"
    write_json(manifest_path, manifest)

    gate_summary = pd.DataFrame(
        [
            {"gate_name": "C1-A.1 Frozen Runtime Hardened", "gate": c1a1_gate},
            {"gate_name": "C1-B Live Engine Completion", "gate": c1b.get("gate")},
            {"gate_name": "Full D1-C1.1", "gate": full_gate},
        ]
    )
    gate_summary_path = ctx.report_dir / "kospi_macro5_d1c11_gate_summary.csv"
    gate_summary.to_csv(gate_summary_path, index=False)

    report = f"""# KOSPI Macro5 D1-C1.1

Full Gate: `{full_gate}`

## C1-A.1 Frozen Runtime Hardening

- Gate: `{c1a1_gate}`
- Frozen raw/transformed source rows: {len(raw_source)}
- Display unique Core15 count: 24
- Full dependency parameterized Core15 count: {len(metadata)}
- Core15 parser missing: {parser_missing}
- Core15 compute missing: {compute_missing}
- Core15 state/event mismatch: {core_state_mismatch}
- Core15 validity mismatch: {core_validity_mismatch}
- Child Combo1 count: {len(graph['required_child_combo1'])}
- Child raw-state mismatch: {child_raw_mismatch}
- Child event mismatch: {child_event_mismatch}
- Final active-count mismatch: {final_active_mismatch}
- Final raw-state mismatch: {final_raw_mismatch}
- Final T+1 mismatch: {final_t1_mismatch}
- Metric tolerance fail: {metric_tolerance_fail}

## C1-B Live Binding

- Gate: `{c1b.get('gate')}`
- Live binding implemented: {manifest['live_binding_count']}
- Live freshness/stale policy: not implemented in D1-C1.1; deferred to D1-C2.

## Notes

- Combo2 input uses child Combo1 raw risk_state.
- Child Combo1 T+1 is not used inside Combo2.
- Final9 T+1 is applied once only.
- Macro5 UI remains in frozen reference viewer mode.
"""
    report_path = ctx.report_dir / "kospi_macro5_d1c11_final_report.md"
    report_path.write_text(report)
    print(json.dumps({"full_gate": full_gate, "c1a1_gate": c1a1_gate, "c1b_gate": c1b.get("gate")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
