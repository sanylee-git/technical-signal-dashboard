from __future__ import annotations

import json
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kospi_macro5_runtime.cloud_probe import run_kospi_macro5_cloud_probe
from kospi_macro5_runtime.engine import sha256_file, sha256_text


FIXED_AS_OF_UTC = datetime(2026, 8, 2, 7, 32, tzinfo=timezone.utc)
TOKEN_PATH = Path(tempfile.gettempdir()) / "kospi_macro5_d1c2b_probe_token.txt"


RUNTIME_CODE = [
    "technical_signal_dashboard.py",
    "kospi_macro5_runtime/calendar_asset.py",
    "kospi_macro5_runtime/canonical_registry.py",
    "kospi_macro5_runtime/cloud_probe.py",
    "kospi_macro5_runtime/core15.py",
    "kospi_macro5_runtime/engine.py",
    "kospi_macro5_runtime/environment_fingerprint.py",
    "kospi_macro5_runtime/freshness.py",
    "kospi_macro5_runtime/freshness_contracts.py",
    "kospi_macro5_runtime/freshness_snapshot.py",
    "kospi_macro5_runtime/krx_calendar.py",
    "kospi_macro5_runtime/last_known_good.py",
    "kospi_macro5_runtime/live_availability.py",
    "kospi_macro5_runtime/live_contracts.py",
    "kospi_macro5_runtime/live_engine.py",
    "kospi_macro5_runtime/live_sources.py",
    "kospi_macro5_runtime/live_tail.py",
    "kospi_macro5_runtime/nfci_schedule.py",
    "kospi_macro5_runtime/provider_dates.py",
    "kospi_macro5_runtime/retry.py",
    "kospi_macro5_runtime/snapshot.py",
    "kospi_macro5_runtime/source_consistency.py",
    "kospi_macro5_runtime/streamlit_cloud_probe_bridge.py",
    "kospi_macro5_runtime/validity.py",
]

RUNTIME_ASSET = [
    "kospi_macro5_assets/kospi_d1c1_dependency_graph.json",
    "kospi_macro5_assets/kospi_d1c1_required_core15_metadata.parquet",
    "kospi_macro5_assets/kospi_d1c1a2_availability_adjusted_transformed_source_base.parquet",
    "kospi_macro5_assets/kospi_d1c2a1_cache_bypass_contract.json",
    "kospi_macro5_assets/kospi_d1c2a1_cloud_probe_contract.json",
    "kospi_macro5_assets/kospi_d1c2a1_freshness_allowlist.json",
    "kospi_macro5_assets/kospi_d1c2a1_nfci_release_contract.json",
    "kospi_macro5_assets/kospi_d1c2a1_provider_date_contract.json",
    "kospi_macro5_assets/kospi_d1c2a1_source_consistency_contract.json",
    "kospi_macro5_assets/kospi_d1c2a2r_krx_calendar_asset.parquet",
    "kospi_macro5_assets/kospi_d1c2a2r_krx_calendar_contract.json",
    "kospi_macro5_assets/kospi_final9_candidate_metrics.csv",
    "kospi_macro5_assets/kospi_final9_component_dictionary.json",
    "kospi_macro5_assets/kospi_final9_dashboard_manifest.json",
]

TEST_ONLY = [
    "scripts/run_kospi_macro5_d1c2b_local_release.py",
    "tests/test_kospi_macro5_d1c2b_cloud_probe_bridge.py",
]

REPORT_ONLY = [
    "reports/kospi_macro5_d1c2b_preflight.md",
    "reports/kospi_macro5_d1c2b_gate_summary.csv",
    "reports/kospi_macro5_d1c2b_manifest.json",
    "reports/kospi_macro5_d1c2b_local_fixed_probe.json",
    "reports/kospi_macro5_d1c2b_local_current_probe.json",
]


def main() -> None:
    reports = ROOT / "reports"
    assets = ROOT / "kospi_macro5_assets"
    reports.mkdir(exist_ok=True)
    assets.mkdir(exist_ok=True)
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(secrets.token_urlsafe(32) + "\n")
        TOKEN_PATH.chmod(0o600)

    dep_manifest_path = assets / "kospi_d1c2b_runtime_dependency_manifest.json"
    dependency_rows = _dependency_rows()
    dep_manifest = {
        "research_stage": "D1-C2B_KOSPI_MACRO5_STREAMLIT_CLOUD_FRESHNESS_PARITY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_worktree_path": "LOCAL_RELEASE_WORKTREE_REDACTED",
        "dependency_file_count": len(dependency_rows),
        "runtime_required_count": sum(1 for row in dependency_rows if row["runtime_required"]),
        "commit_candidate_count": sum(1 for row in dependency_rows if row["commit_candidate"]),
        "total_runtime_asset_bytes": sum(row["size_bytes"] for row in dependency_rows if row["category"] == "RUNTIME_ASSET"),
        "max_file_bytes": max([row["size_bytes"] for row in dependency_rows] or [0]),
        "files": dependency_rows,
    }
    dep_manifest_path.write_text(json.dumps(dep_manifest, ensure_ascii=False, indent=2) + "\n")
    dependency_rows = _dependency_rows(extra_runtime_assets=[str(dep_manifest_path.relative_to(ROOT))])
    dep_manifest.update(
        {
            "dependency_file_count": len(dependency_rows),
            "runtime_required_count": sum(1 for row in dependency_rows if row["runtime_required"]),
            "commit_candidate_count": sum(1 for row in dependency_rows if row["commit_candidate"]),
            "total_runtime_asset_bytes": sum(row["size_bytes"] for row in dependency_rows if row["category"] == "RUNTIME_ASSET"),
            "max_file_bytes": max([row["size_bytes"] for row in dependency_rows] or [0]),
            "files": dependency_rows,
        }
    )
    dep_manifest_path.write_text(json.dumps(dep_manifest, ensure_ascii=False, indent=2) + "\n")

    fixed = run_kospi_macro5_cloud_probe(as_of_utc=FIXED_AS_OF_UTC, output_path=reports / "kospi_macro5_d1c2b_local_fixed_probe.json")
    current = run_kospi_macro5_cloud_probe(output_path=reports / "kospi_macro5_d1c2b_local_current_probe.json")

    prev = _read_json(assets / "kospi_d1c2a2r_cloud_probe_fixed.json")
    prev_manifest = _read_json(reports / "kospi_macro5_d1c2a2r_manifest.json")
    fixed_hash = fixed["hashes"]["candidate_semantic_hash"]
    prev_hash = (
        (prev.get("hashes") or {}).get("candidate_semantic_hash")
        or (prev.get("hashes") or {}).get("candidate_snapshot_hash")
        or prev_manifest.get("candidate_semantic_hash")
    )
    source_count = len(fixed.get("sources", []))
    candidate_count = len(fixed.get("candidates", []))
    freshness_qualified = sum(1 for row in fixed.get("candidates", []) if row.get("freshness_qualified") is True)
    calculable = sum(1 for row in fixed.get("candidates", []) if row.get("calculable") is True)
    gate_checks = {
        "dependency_missing": sum(1 for row in dependency_rows if row["missing"] and row["runtime_required"]),
        "report_only_missing_at_manifest_build": sum(1 for row in dependency_rows if row["missing"] and row["category"] == "REPORT_ONLY"),
        "source_count": source_count,
        "candidate_count": candidate_count,
        "fixed_final9_calculable": calculable,
        "fixed_final9_freshness_qualified": freshness_qualified,
        "fixed_candidate_semantic_hash": fixed_hash,
        "previous_candidate_semantic_hash": prev_hash,
        "fixed_candidate_semantic_match_vs_c2a2r": True if not prev_hash else fixed_hash == prev_hash,
        "current_source_count": len(current.get("sources", [])),
        "current_candidate_count": len(current.get("candidates", [])),
        "current_candidate_semantic_hash": current["hashes"]["candidate_semantic_hash"],
        "token_file": str(TOKEN_PATH),
    }
    gate = (
        gate_checks["dependency_missing"] == 0
        and source_count == 11
        and candidate_count == 9
        and calculable == 9
        and freshness_qualified == 9
        and gate_checks["fixed_candidate_semantic_match_vs_c2a2r"]
    )
    gate_name = "PASS_KOSPI_MACRO5_D1C2B1_LOCAL_RELEASE_PARITY_READY" if gate else "BLOCKED_KOSPI_MACRO5_D1C2B1_LOCAL_RELEASE_PARITY"
    pd.DataFrame(
        [{"check": key, "value": value} for key, value in gate_checks.items()]
        + [{"check": "gate", "value": gate_name}]
    ).to_csv(reports / "kospi_macro5_d1c2b_gate_summary.csv", index=False)

    manifest = {
        "research_stage": "D1-C2B_KOSPI_MACRO5_STREAMLIT_CLOUD_FRESHNESS_PARITY",
        "previous_gate": "PASS_KOSPI_MACRO5_D1C2A2R_XKRX_CALENDAR_CONTRACT_CLOSED_READY_FOR_D1C2B",
        "c2b0_gate": "PASS_KOSPI_MACRO5_D1C2B0_RELEASE_PACKAGE_READY" if gate_checks["dependency_missing"] == 0 else "BLOCKED_KOSPI_MACRO5_D1C2B0_RELEASE_PACKAGE",
        "c2b1_gate": gate_name,
        "release_worktree_path": str(ROOT),
        "release_base_commit": _git(["rev-parse", "HEAD"]),
        "origin_main_commit": _git(["rev-parse", "origin/main"]),
        "fixed_as_of_utc": FIXED_AS_OF_UTC.isoformat(),
        "runtime_dependency_manifest": str(dep_manifest_path.relative_to(ROOT)),
        "local_fixed_probe": "reports/kospi_macro5_d1c2b_local_fixed_probe.json",
        "local_current_probe": "reports/kospi_macro5_d1c2b_local_current_probe.json",
        "gate_checks": gate_checks,
        "cloud_probe_streamlit_cloud_executed": False,
        "ui_connected_to_live_engine": False,
        "macro5_page_mode": "FROZEN_REFERENCE_VIEWER",
        "actual_trading_ready": False,
        "official_operating_model": False,
        "shadow_mode": True,
    }
    (reports / "kospi_macro5_d1c2b_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n")
    (reports / "kospi_macro5_d1c2b_preflight.md").write_text(_report_text(manifest, dep_manifest), encoding="utf-8")
    if not gate:
        raise SystemExit(gate_name)
    print(gate_name)


def _dependency_rows(extra_runtime_assets: list[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    category_map = {
        "RUNTIME_CODE": RUNTIME_CODE,
        "RUNTIME_ASSET": RUNTIME_ASSET + list(extra_runtime_assets or []),
        "TEST_ONLY": TEST_ONLY,
        "REPORT_ONLY": REPORT_ONLY,
    }
    for category, files in category_map.items():
        for rel in files:
            path = ROOT / rel
            rows.append(
                {
                    "relative_path": rel,
                    "category": category,
                    "required_by": "streamlit_cloud_probe" if category.startswith("RUNTIME") else "local_release_validation",
                    "source_manifest": "d1c2b_dependency_closure",
                    "source_sha256": sha256_file(path) if path.exists() and path.is_file() else "",
                    "release_sha256": sha256_file(path) if path.exists() and path.is_file() else "",
                    "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
                    "runtime_required": category in {"RUNTIME_CODE", "RUNTIME_ASSET"},
                    "commit_candidate": category in {"RUNTIME_CODE", "RUNTIME_ASSET", "TEST_ONLY"},
                    "missing": not path.exists(),
                    "reason": "needed by hidden Streamlit probe" if category.startswith("RUNTIME") else "validation evidence only",
                }
            )
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def _report_text(manifest: dict[str, Any], dep_manifest: dict[str, Any]) -> str:
    checks = manifest["gate_checks"]
    return "\n".join(
        [
            "# KOSPI Macro5 D1-C2B Local Release Probe",
            "",
            f"- C2B0 Gate: {manifest['c2b0_gate']}",
            f"- C2B1 Gate: {manifest['c2b1_gate']}",
            f"- Release worktree: {manifest['release_worktree_path']}",
            f"- Release base commit: {manifest['release_base_commit']}",
            f"- Runtime dependency files: {dep_manifest['dependency_file_count']}",
            f"- Runtime asset bytes: {dep_manifest['total_runtime_asset_bytes']}",
            f"- Fixed source count: {checks['source_count']} / 11",
            f"- Fixed candidate count: {checks['candidate_count']} / 9",
            f"- Fixed Final9 calculable: {checks['fixed_final9_calculable']} / 9",
            f"- Fixed freshness-qualified: {checks['fixed_final9_freshness_qualified']} / 9",
            f"- Fixed candidate semantic hash: `{checks['fixed_candidate_semantic_hash']}`",
            f"- Previous C2A2R semantic hash: `{checks['previous_candidate_semantic_hash']}`",
            f"- Token file: `{checks['token_file']}`",
            "",
            "Cloud probe has not been executed by this local report.",
        ]
    ) + "\n"


if __name__ == "__main__":
    main()
