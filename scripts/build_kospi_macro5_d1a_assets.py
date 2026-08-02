from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
KOSPI_ROOT = DASHBOARD_ROOT.parent / "macro_dashboard_kospi"
ASSET_DIR = DASHBOARD_ROOT / "kospi_macro5_assets"
REPORT_DIR = DASHBOARD_ROOT / "reports"

FINAL9 = [
    {"slot": 1, "suffix": "b984a8e5", "model_type": "combo1", "role": "균형 코어"},
    {"slot": 2, "suffix": "93919287", "model_type": "combo1", "role": "방어 코어"},
    {"slot": 3, "suffix": "ad654f06", "model_type": "combo1", "role": "공격 수익"},
    {"slot": 4, "suffix": "9f010558", "model_type": "combo1", "role": "고수익·독립"},
    {"slot": 5, "suffix": "824f7336", "model_type": "combo2", "role": "균형·강건"},
    {"slot": 6, "suffix": "b8b4a80e", "model_type": "combo2", "role": "성과 코어"},
    {"slot": 7, "suffix": "fdecfd9e", "model_type": "combo2", "role": "MDD·Calmar 앵커"},
    {"slot": 8, "suffix": "d49b44bb", "model_type": "combo2", "role": "최상위 성과"},
    {"slot": 9, "suffix": "f4789711", "model_type": "combo2", "role": "다양성·안정 보완"},
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DASHBOARD_ROOT))
    except ValueError:
        try:
            return str(path.relative_to(KOSPI_ROOT))
        except ValueError:
            return str(path)


def load_manifest(name: str) -> dict:
    path = KOSPI_ROOT / "manifests" / name
    data = json.loads(path.read_text())
    data["_manifest_path"] = path
    data["_manifest_sha256"] = sha256_file(path)
    return data


def output_path(manifest: dict, key: str) -> Path:
    value = (manifest.get("output_files") or manifest.get("outputs") or {})[key]
    if isinstance(value, dict):
        value = value["path"]
    return KOSPI_ROOT / value


def pick_row_by_suffix(df: pd.DataFrame, id_col: str, suffix: str) -> pd.Series:
    hits = df[df[id_col].astype(str).str.contains(suffix, case=False, na=False)].copy()
    if len(hits) != 1:
        raise RuntimeError(f"{suffix} expected one match in {id_col}, got {len(hits)}")
    return hits.iloc[0]


def combo1_source_frames() -> dict[str, tuple[pd.DataFrame, dict, str]]:
    a3 = load_manifest("stage5e_a3_latest_combo1_cycle_aware_review20.json")
    a2 = load_manifest("stage5e_a2_latest_combo1_performance_relaxed_kl_review20.json")
    b1 = load_manifest("stage5e_b1_latest_combo2_cycle_aware_material_review64.json")
    return {
        "stage05e_a3_cycle_aware_review20": (
            pd.read_csv(output_path(a3, "review20_csv")),
            a3,
            "review20_csv",
        ),
        "stage05e_a2_relaxed_review20": (
            pd.read_csv(output_path(a2, "relaxed_review20_csv")),
            a2,
            "relaxed_review20_csv",
        ),
        "stage05e_b1_material_main32": (
            pd.read_csv(output_path(b1, "cycle_aware_main32_csv")),
            b1,
            "cycle_aware_main32_csv",
        ),
    }


def resolve_combo1(suffix: str) -> tuple[pd.Series, dict, str, str]:
    # Prefer standalone/cycle-aware sources for display candidates, then material main32.
    order = [
        "stage05e_a3_cycle_aware_review20",
        "stage05e_a2_relaxed_review20",
        "stage05e_b1_material_main32",
    ]
    frames = combo1_source_frames()
    matches: list[tuple[str, pd.Series, dict, str]] = []
    for label in order:
        df, manifest, key = frames[label]
        hits = df[df["combo1_id"].astype(str).str.contains(suffix, case=False, na=False)].copy()
        if len(hits):
            matches.append((label, hits.iloc[0], manifest, key))
    if not matches:
        raise RuntimeError(f"combo1 suffix not resolved: {suffix}")
    label, row, manifest, key = matches[0]
    return row, manifest, label, key


def resolve_combo2(suffix: str) -> tuple[pd.Series, dict, str]:
    m = load_manifest("stage7c2_latest_combo2_union58_decision10_proposal.json")
    df = pd.read_csv(output_path(m, "recommended_proposed_decision10_csv"))
    row = pick_row_by_suffix(df, "candidate_id", suffix)
    return row, m, "recommended_proposed_decision10_csv"


def load_indicator_risk_state(indicator_id: str) -> pd.DataFrame:
    base = (
        KOSPI_ROOT
        / "outputs/kospi/run_20260731T005207Z_stage03c_core15_extended_signal_bank_v1"
        / "03c_core15_extended_signal_bank/signals_by_indicator"
    )
    path = base / f"{indicator_id}_risk_state.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def compute_combo1_raw_state(row: pd.Series) -> pd.DataFrame:
    components = str(row["candidate_ids_key"]).split("|")
    merged = None
    for cid in components:
        indicator_id = cid.split("__")[0]
        df = load_indicator_risk_state(indicator_id)
        if cid not in df.columns:
            raise RuntimeError(f"component risk_state not found: {cid}")
        one = df[["date", cid]]
        merged = one if merged is None else merged.merge(one, on="date", how="inner")
    values = merged[components].fillna(0).astype("uint8").to_numpy()
    on_count = values.sum(axis=1)
    k = int(row["K"])
    l = int(row["L"])
    raw_state = []
    current = 0
    for count in on_count:
        if current == 0 and count >= k:
            current = 1
        elif current == 1 and count <= l:
            current = 0
        raw_state.append(current)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(merged["date"]),
            "raw_risk_state": pd.Series(raw_state, dtype="int8"),
            "on_count": pd.Series(on_count, dtype="int16"),
        }
    )
    out["t1_position"] = (1 - out["raw_risk_state"].shift(1).fillna(0)).astype("int8")
    return out


def compute_state_hash(df: pd.DataFrame, col: str = "raw_risk_state") -> str:
    tmp = df[["date", col]].copy()
    tmp["date"] = pd.to_datetime(tmp["date"]).dt.strftime("%Y-%m-%d")
    payload = "\n".join(f"{d},{int(v)}" for d, v in tmp[["date", col]].itertuples(index=False)).encode()
    return sha256_bytes(payload)


def macro4_slice_hash() -> dict:
    path = DASHBOARD_ROOT / "technical_signal_dashboard.py"
    lines = path.read_text(errors="ignore").splitlines()
    start = next(i for i, line in enumerate(lines) if "def render_macro4_combo_section" in line)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if lines[i].startswith("    elif page ==") or stripped.startswith("def render_macro5"):
            end = i
            break
    text = "\n".join(lines[start:end])
    return {
        "path": rel(path),
        "start_line": start + 1,
        "end_line": end,
        "sha256": sha256_bytes(text.encode()),
        "line_count": end - start,
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    safe = df.copy().astype(str)
    headers = list(safe.columns)
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for values in safe.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(str(v).replace("|", "\\|") for v in values) + " |")
    return "\n".join(rows)


def main() -> None:
    ASSET_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    records = []
    signals = []
    component_dictionary = {}
    parity_checks = []

    # Reference bank for two Combo1 candidates that overlap Main32.
    s6 = load_manifest("stage6a_latest_combo2_m2_m5_exhaustive_review.json")
    raw_dict_path = output_path(s6, "raw_state_dictionary")
    raw_bank_path = output_path(s6, "raw_state_bank")
    raw_dict = pd.read_csv(raw_dict_path)
    raw_bank = pd.read_parquet(raw_bank_path)
    raw_bank["date"] = pd.to_datetime(raw_bank["date"]).dt.strftime("%Y-%m-%d")

    for item in FINAL9:
        suffix = item["suffix"]
        if item["model_type"] == "combo1":
            row, source_manifest, source_label, source_key = resolve_combo1(suffix)
            cid = row["combo1_id"]
            computed = compute_combo1_raw_state(row)
            computed.insert(1, "candidate_id", cid)
            computed.insert(2, "model_type", "combo1")
            computed.insert(3, "slot", item["slot"])
            signals.append(computed)
            source_signal_parity = "RECOMPUTED_FROM_CORE15_COMPONENTS"

            hit_idx = raw_dict.index[raw_dict["combo1_id"].astype(str) == cid].tolist()
            if hit_idx:
                col = f"c{hit_idx[0] + 1:02d}"
                ref = raw_bank[["date", col]].rename(columns={col: "reference_raw_risk_state"})
                cmp = computed.assign(date=computed["date"].dt.strftime("%Y-%m-%d")).merge(ref, on="date", how="inner")
                mismatch = int((cmp["raw_risk_state"].astype(int) != cmp["reference_raw_risk_state"].astype(int)).sum())
                source_signal_parity = "PASS_VS_STAGE06A_RAW_BANK" if mismatch == 0 else "FAIL_VS_STAGE06A_RAW_BANK"
                parity_checks.append(
                    {
                        "candidate_id": cid,
                        "reference_source": "stage06a_combo1_main32_raw_risk_state_bank",
                        "common_rows": int(len(cmp)),
                        "mismatch_count": mismatch,
                        "reference_column": col,
                    }
                )
            else:
                parity_checks.append(
                    {
                        "candidate_id": cid,
                        "reference_source": "no_stored_raw_bank_match",
                        "common_rows": 0,
                        "mismatch_count": None,
                        "reference_column": None,
                    }
                )

            component_dictionary[cid] = {
                "model_type": "combo1",
                "component_ids": str(row["candidate_ids_key"]).split("|"),
                "family_set_key": row.get("family_set_key"),
                "K": int(row["K"]),
                "L": int(row["L"]),
            }
            metrics = row
            signal_hash = compute_state_hash(computed)
        else:
            row, source_manifest, source_key = resolve_combo2(suffix)
            source_label = "stage07c2_proposed_decision10"
            cid = row["candidate_id"]
            daily = pd.read_parquet(output_path(source_manifest, "decision10_daily_signals"))
            daily = daily[daily["candidate_id"] == cid].copy()
            if daily.empty:
                raise RuntimeError(f"combo2 daily signal not found: {cid}")
            daily["model_type"] = "combo2"
            daily["slot"] = item["slot"]
            signals.append(daily[["date", "candidate_id", "model_type", "slot", "raw_risk_state", "t1_position"]])
            source_signal_parity = "PASS_STORED_STAGE07C2_DAILY_SIGNAL"
            component_dictionary[cid] = {
                "model_type": "combo2",
                "component_ids": str(row.get("component_ids_key", "")).split("|"),
                "family_set_key": row.get("family_set_compact_hash"),
                "K": int(row["K"]),
                "L": int(row["L"]),
            }
            metrics = row
            signal_hash = compute_state_hash(daily)

        records.append(
            {
                "slot": item["slot"],
                "model_type": item["model_type"],
                "role": item["role"],
                "suffix": suffix,
                "candidate_id": cid,
                "m_or_n": int(metrics.get("m", metrics.get("n"))),
                "K": int(metrics["K"]),
                "L": int(metrics["L"]),
                "cagr": float(metrics.get("cagr")),
                "mdd": float(metrics.get("mdd")),
                "calmar": float(metrics.get("calmar")),
                "risk_off_ratio": float(metrics.get("risk_off_ratio")),
                "annual_turnover": float(metrics.get("annual_turnover")),
                "signal_hash_source": str(metrics.get("signal_hash", "")),
                "reference_signal_hash": signal_hash,
                "source_label": source_label,
                "source_manifest": rel(source_manifest["_manifest_path"]),
                "source_manifest_sha256": source_manifest["_manifest_sha256"],
                "source_output_key": source_key,
                "source_signal_parity": source_signal_parity,
            }
        )

    metrics_df = pd.DataFrame(records)
    signals_df = pd.concat(signals, ignore_index=True)
    signals_df["date"] = pd.to_datetime(signals_df["date"])
    signals_df = signals_df.sort_values(["slot", "date"]).reset_index(drop=True)

    metrics_path = ASSET_DIR / "kospi_final9_candidate_metrics.csv"
    signals_path = ASSET_DIR / "kospi_final9_reference_signals.parquet"
    components_path = ASSET_DIR / "kospi_final9_component_dictionary.json"
    contract_path = ASSET_DIR / "kospi_final9_source_contract.json"
    manifest_path = ASSET_DIR / "kospi_final9_dashboard_manifest.json"
    checksums_path = ASSET_DIR / "checksums.json"
    parity_path = ASSET_DIR / "kospi_final9_parity_checks.csv"

    metrics_df.to_csv(metrics_path, index=False)
    signals_df.to_parquet(signals_path, index=False)
    pd.DataFrame(parity_checks).to_csv(parity_path, index=False)
    write_json(components_path, component_dictionary)

    source_contract = {
        "market": "KOSPI",
        "benchmark": "KOSPI composite close",
        "risk_state_semantics": "risk_state=1 means Risk-off/non-invested; risk_state=0 means Risk-on/investable",
        "signal_semantics": "RAW_RISK_STATE; t1_position[t] = 1 - raw_risk_state[t-1]",
        "evaluation_start": "2008-04-01",
        "evaluation_end": "2026-07-28",
        "transaction_cost_bps": 10,
        "cash_return_applied": False,
        "official_operating_model": False,
        "shadow_mode": True,
        "manual_user_selected_final9": True,
        "source_selection_note": (
            "User manually selected Combo1 Core4 and Combo2 Core5 after reviewing "
            "Stage07C.2 Proposed Decision10 and Combo1 review outputs. This is a shadow dashboard asset, "
            "not an official operating model."
        ),
    }
    write_json(contract_path, source_contract)

    checksum_targets = [metrics_path, signals_path, components_path, contract_path, parity_path]
    checksums = {path.name: {"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in checksum_targets}
    write_json(checksums_path, checksums)

    unresolved = metrics_df[metrics_df["source_signal_parity"].str.startswith("FAIL")]
    no_direct_reference = pd.DataFrame(parity_checks)
    no_direct_reference = no_direct_reference[no_direct_reference["reference_source"] == "no_stored_raw_bank_match"]
    gate = "PASS_KOSPI_MACRO5_D1A_RUNTIME_ASSET_READY"
    if not unresolved.empty:
        gate = "BLOCKED_KOSPI_MACRO5_REFERENCE_SIGNAL_PARITY_FAIL"
    elif len(no_direct_reference):
        gate = "PASS_WITH_RECOMPUTED_COMBO1_REFERENCE_SIGNALS"

    macro4 = macro4_slice_hash()
    manifest = {
        "gate": gate,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_stage": "D1-A_RUNTIME_ASSET_AND_HISTORICAL_PARITY",
        "official_operating_model": False,
        "dashboard_applied": False,
        "shadow_mode": True,
        "manual_user_selected_final9": True,
        "candidate_count": int(len(metrics_df)),
        "combo1_count": int((metrics_df["model_type"] == "combo1").sum()),
        "combo2_count": int((metrics_df["model_type"] == "combo2").sum()),
        "reference_signal_rows": int(len(signals_df)),
        "reference_signal_date_start": signals_df["date"].min().strftime("%Y-%m-%d"),
        "reference_signal_date_end": signals_df["date"].max().strftime("%Y-%m-%d"),
        "macro4_reference_hash": macro4,
        "output_files": {
            "candidate_metrics": rel(metrics_path),
            "reference_signals": rel(signals_path),
            "component_dictionary": rel(components_path),
            "source_contract": rel(contract_path),
            "parity_checks": rel(parity_path),
            "checksums": rel(checksums_path),
        },
    }
    write_json(manifest_path, manifest)

    report_path = REPORT_DIR / "kospi_macro5_d1a_runtime_asset_parity_report.md"
    lines = [
        "# KOSPI Macro5 D1-A Runtime Asset & Historical Parity",
        "",
        f"- Gate: `{gate}`",
        "- Scope: UI code was not modified in D1-A.",
        "- Final9 status: `manual_user_selected_final9=true`, `official_operating_model=false`, `shadow_mode=true`.",
        f"- Candidates: {len(metrics_df)} total ({manifest['combo1_count']} Combo1, {manifest['combo2_count']} Combo2)",
        f"- Reference signal rows: {len(signals_df):,} ({manifest['reference_signal_date_start']} ~ {manifest['reference_signal_date_end']})",
        "",
        "## Source Resolution",
        markdown_table(
            metrics_df[
                [
                    "slot",
                    "model_type",
                    "role",
                    "candidate_id",
                    "K",
                    "L",
                    "source_label",
                    "source_signal_parity",
                ]
            ]
        ),
        "",
        "## Combo1 Stored Reference Parity",
        markdown_table(pd.DataFrame(parity_checks)),
        "",
        "## Macro4 Reference",
        f"- Macro4 render slice: `{macro4['path']}:{macro4['start_line']}`",
        f"- Macro4 slice hash: `{macro4['sha256']}`",
        "",
        "## D1-B Guardrails",
        "- Clone Macro4 structure only after this D1-A asset is accepted.",
        "- Use `macro5_kospi_*` namespace for session_state, widget keys, cache, debug events, and loaders.",
        "- Do not share mutable Macro4 preset dictionaries or cache keys.",
        "- Keep `official_operating_model=false` until separate user approval.",
    ]
    report_path.write_text("\n".join(lines) + "\n")

    pre_path = REPORT_DIR / "kospi_macro5_preimplementation_audit.md"
    pre_path.write_text(
        "\n".join(
            [
                "# KOSPI Macro5 Preimplementation Audit",
                "",
                "- D1-A created runtime assets only; `technical_signal_dashboard.py` was not edited.",
                "- Macro4 and Macro5 must be state/cache isolated in D1-B.",
                "- Allowed D1-B changes: new Macro5 KOSPI route/renderer, KOSPI asset loader, KOSPI signal adapter, KOSPI-only widget keys.",
                "- Forbidden D1-B changes: Macro4 design/function redesign, Macro4 cache/session mutation, shared mutable preset dictionaries.",
                "",
                f"- Macro4 slice hash: `{macro4['sha256']}`",
            ]
        )
        + "\n"
    )

    print(json.dumps({"gate": gate, "manifest": rel(manifest_path), "report": rel(report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
