from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
KOSPI_ROOT = DASHBOARD_ROOT.parent / "macro_dashboard_kospi"
ASSET_DIR = DASHBOARD_ROOT / "kospi_macro5_assets"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DASHBOARD_ROOT))
    except ValueError:
        try:
            return "macro_dashboard_kospi/" + str(path.relative_to(KOSPI_ROOT))
        except ValueError:
            return path.name


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def normalize_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out


def load_indicator_state(indicator_id: str) -> pd.DataFrame:
    path = (
        KOSPI_ROOT
        / "outputs/kospi/run_20260731T005207Z_stage03c_core15_extended_signal_bank_v1"
        / "03c_core15_extended_signal_bank/signals_by_indicator"
        / f"{indicator_id}_risk_state.parquet"
    )
    df = normalize_date(pd.read_parquet(path))
    return df


def component_label(component_id: str) -> str:
    if "__" not in component_id:
        return component_id
    family, param = component_id.split("__", 1)
    return f"{family} · {param.split('__')[0]}"


def main() -> None:
    ASSET_DIR.mkdir(exist_ok=True)

    d1a_manifest = read_json(ASSET_DIR / "kospi_final9_dashboard_manifest.json")
    metrics = pd.read_csv(ASSET_DIR / "kospi_final9_candidate_metrics.csv")
    signals = normalize_date(pd.read_parquet(ASSET_DIR / "kospi_final9_reference_signals.parquet"))
    components = read_json(ASSET_DIR / "kospi_final9_component_dictionary.json")

    frozen_path = (
        KOSPI_ROOT
        / "data/frozen/kospi/snapshot_stage03c_extended_19961211_20260728_9d7d552362bf"
        / "frozen_kospi_macro_extended.parquet"
    )
    frozen = normalize_date(pd.read_parquet(frozen_path, columns=["date", "kospi_close"]))
    date_min = signals["date"].min()
    date_max = signals["date"].max()
    benchmark = frozen[(frozen["date"] >= date_min) & (frozen["date"] <= date_max)].copy()
    benchmark["kospi_close"] = benchmark["kospi_close"].astype(float)
    benchmark_path = ASSET_DIR / "kospi_final9_benchmark_close.parquet"
    benchmark.to_parquet(benchmark_path, index=False)

    s6_manifest_path = KOSPI_ROOT / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json"
    s6_manifest = read_json(s6_manifest_path)
    s6_outputs = s6_manifest["output_files"]
    raw_dict_path = KOSPI_ROOT / s6_outputs["raw_state_dictionary"]
    raw_bank_path = KOSPI_ROOT / s6_outputs["raw_state_bank"]
    raw_dict = pd.read_csv(raw_dict_path).reset_index(drop=True)
    raw_bank = normalize_date(pd.read_parquet(raw_bank_path))

    component_rows = []
    indicator_cache: dict[str, pd.DataFrame] = {}

    def add_component(parent_id: str, parent_slot: int, parent_type: str, comp_id: str, order: int) -> None:
        if comp_id.startswith("combo1_"):
            hits = raw_dict.index[raw_dict["combo1_id"].astype(str) == comp_id].tolist()
            if not hits:
                return
            col = f"c{hits[0] + 1:02d}"
            tmp = raw_bank[["date", col]].rename(columns={col: "component_risk_state"})
            meta = raw_dict.iloc[hits[0]]
            tmp["component_active_count"] = pd.NA
            comp_k = int(meta["K"])
            comp_l = int(meta["L"])
            reference_type = "combo1_main32_raw_state_bank"
        else:
            indicator_id = comp_id.split("__")[0]
            if indicator_id not in indicator_cache:
                indicator_cache[indicator_id] = load_indicator_state(indicator_id)
            table = indicator_cache[indicator_id]
            if comp_id not in table.columns:
                return
            tmp = table[["date", comp_id]].rename(columns={comp_id: "component_risk_state"})
            tmp["component_active_count"] = pd.NA
            comp_k = pd.NA
            comp_l = pd.NA
            reference_type = "core15_component_risk_state"
        tmp = tmp[(tmp["date"] >= date_min) & (tmp["date"] <= date_max)].copy()
        tmp["parent_candidate_id"] = parent_id
        tmp["parent_slot"] = parent_slot
        tmp["parent_model_type"] = parent_type
        tmp["component_id"] = comp_id
        tmp["component_order"] = order
        tmp["component_label"] = component_label(comp_id)
        tmp["component_K"] = comp_k
        tmp["component_L"] = comp_l
        tmp["valid_signal"] = tmp["component_risk_state"].notna()
        tmp["reference_type"] = reference_type
        component_rows.append(tmp)

    for rec in metrics.to_dict("records"):
        cid = rec["candidate_id"]
        comp_ids = components[cid]["component_ids"]
        for idx, comp_id in enumerate(comp_ids, start=1):
            add_component(cid, int(rec["slot"]), rec["model_type"], comp_id, idx)

    component_df = pd.concat(component_rows, ignore_index=True)
    component_df["component_risk_state"] = component_df["component_risk_state"].astype("Int8")
    component_path = ASSET_DIR / "kospi_final9_component_reference_signals.parquet"
    component_df.to_parquet(component_path, index=False)

    snapshot_rows = []
    latest_date = signals["date"].max()
    for rec in metrics.to_dict("records"):
        cid = rec["candidate_id"]
        one = signals[signals["candidate_id"] == cid].copy().sort_values("date")
        one["start_event"] = ((one["raw_risk_state"] == 1) & (one["raw_risk_state"].shift(1).fillna(0) == 0)).astype("int8")
        one["end_event"] = ((one["raw_risk_state"] == 0) & (one["raw_risk_state"].shift(1).fillna(0) == 1)).astype("int8")
        latest = one.iloc[-1]
        change = one[one["raw_risk_state"].ne(one["raw_risk_state"].shift(1))]
        last_change_date = change.iloc[-1]["date"] if len(change) else latest_date
        duration = int((one["date"] >= last_change_date).sum())
        comp_latest = component_df[
            (component_df["parent_candidate_id"] == cid) & (component_df["date"] == latest_date)
        ]
        active_count = int(comp_latest["component_risk_state"].fillna(0).astype(int).sum()) if len(comp_latest) else None
        snapshot_rows.append(
            {
                "candidate_id": cid,
                "slot": int(rec["slot"]),
                "model_type": rec["model_type"],
                "role": rec["role"],
                "suffix": rec["suffix"],
                "date": latest_date,
                "raw_risk_state": int(latest["raw_risk_state"]),
                "t1_position": int(latest["t1_position"]),
                "active_count": active_count,
                "K": int(rec["K"]),
                "L": int(rec["L"]),
                "last_transition_date": last_change_date,
                "current_state_trading_days": duration,
                "reference_type": rec["source_signal_parity"],
                "valid": True,
            }
        )
    snapshot = pd.DataFrame(snapshot_rows)
    snapshot_path = ASSET_DIR / "kospi_final9_ui_snapshot_reference.parquet"
    snapshot.to_parquet(snapshot_path, index=False)

    d1b_files = {
        "benchmark_close": benchmark_path,
        "component_reference_signals": component_path,
        "ui_snapshot_reference": snapshot_path,
    }
    manifest = {
        "gate": "PASS_KOSPI_MACRO5_D1B_UI_ASSET_COVERAGE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_stage": "D1-B_UI_SUPPORT_ASSETS",
        "input_d1a_gate": d1a_manifest["gate"],
        "official_operating_model": False,
        "dashboard_applied": False,
        "frozen_reference_mode": True,
        "live_extension_connected": False,
        "candidate_count": int(metrics["candidate_id"].nunique()),
        "benchmark_rows": int(len(benchmark)),
        "component_signal_rows": int(len(component_df)),
        "snapshot_rows": int(len(snapshot)),
        "date_start": date_min,
        "date_end": date_max,
        "source_files": {
            "extended_frozen": {
                "path": rel(frozen_path),
                "sha256": sha256_file(frozen_path),
            },
            "stage06a_raw_state_dictionary": {
                "path": rel(raw_dict_path),
                "sha256": sha256_file(raw_dict_path),
            },
            "stage06a_raw_state_bank": {
                "path": rel(raw_bank_path),
                "sha256": sha256_file(raw_bank_path),
            },
        },
        "output_files": {
            key: {
                "path": rel(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for key, path in d1b_files.items()
        },
    }
    manifest_path = ASSET_DIR / "kospi_macro5_d1b_ui_manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps({"gate": manifest["gate"], "manifest": rel(manifest_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
