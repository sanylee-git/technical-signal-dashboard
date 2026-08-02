from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def normalize_date(df: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[column] = pd.to_datetime(out[column]).dt.strftime("%Y-%m-%d")
    return out


@dataclass(frozen=True)
class D1C1Context:
    dashboard_root: Path
    kospi_root: Path | None = None

    @property
    def asset_dir(self) -> Path:
        return self.dashboard_root / "kospi_macro5_assets"

    @property
    def report_dir(self) -> Path:
        return self.dashboard_root / "reports"

    @property
    def macro_root(self) -> Path:
        if self.kospi_root is not None:
            return self.kospi_root
        return self.dashboard_root.parent / "macro_dashboard_kospi"

    def rel_dashboard(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.dashboard_root))
        except ValueError:
            try:
                return "macro_dashboard_kospi/" + str(path.relative_to(self.macro_root))
            except ValueError:
                return str(path)


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} missing: {path}")


def _load_stage06_raw_dictionary(ctx: D1C1Context) -> pd.DataFrame:
    manifest_path = ctx.macro_root / "manifests/stage6a_latest_combo2_m2_m5_exhaustive_review.json"
    _require_file(manifest_path, "stage06a manifest")
    manifest = read_json(manifest_path)
    path = ctx.macro_root / manifest["output_files"]["raw_state_dictionary"]
    _require_file(path, "stage06a raw_state_dictionary")
    return pd.read_csv(path)


def _load_final9_dictionary(ctx: D1C1Context) -> dict[str, Any]:
    path = ctx.asset_dir / "kospi_final9_component_dictionary.json"
    _require_file(path, "Final9 component dictionary")
    return read_json(path)


def build_dependency_graph(ctx: D1C1Context) -> dict[str, Any]:
    final9 = _load_final9_dictionary(ctx)
    raw_dict = _load_stage06_raw_dictionary(ctx)
    raw_by_id = {str(row.combo1_id): row for row in raw_dict.itertuples(index=False)}

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    missing_children: list[str] = []
    required_core: set[str] = set()
    required_child_combo1: set[str] = set()

    for final_id, spec in final9.items():
        nodes[final_id] = {
            "node_type": spec["model_type"],
            "K": int(spec["K"]),
            "L": int(spec["L"]),
            "component_count": len(spec.get("component_ids", [])),
        }
        for child_id in spec.get("component_ids", []):
            edges.append({"parent": final_id, "child": child_id})
            if child_id.startswith("combo1_"):
                required_child_combo1.add(child_id)
                child_row = raw_by_id.get(child_id)
                if child_row is None:
                    missing_children.append(child_id)
                    continue
                child_components = str(child_row.candidate_ids_key).split("|")
                nodes[child_id] = {
                    "node_type": "child_combo1_raw_state",
                    "K": int(child_row.K),
                    "L": int(child_row.L),
                    "component_count": len(child_components),
                    "source": "stage06a_main32_raw_state_dictionary",
                }
                for core_id in child_components:
                    required_core.add(core_id)
                    edges.append({"parent": child_id, "child": core_id})
                    nodes.setdefault(core_id, {"node_type": "core15_component"})
            else:
                required_core.add(child_id)
                nodes.setdefault(child_id, {"node_type": "core15_component"})

    graph = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "final9_count": len(final9),
        "required_child_combo1_count": len(required_child_combo1),
        "required_core15_component_count": len(required_core),
        "dependency_missing_count": len(missing_children),
        "missing_child_combo1_ids": sorted(missing_children),
        "nodes": nodes,
        "edges": edges,
        "required_core15_components": sorted(required_core),
        "required_child_combo1": sorted(required_child_combo1),
    }
    graph["dependency_graph_hash"] = sha256_text(json.dumps(graph, sort_keys=True, default=str))
    return graph


def hysteresis_from_counts(counts: pd.Series, k: int, l: int) -> pd.Series:
    state = 0
    out: list[int] = []
    for value in counts.fillna(0).astype(int).tolist():
        if state == 0 and value >= k:
            state = 1
        elif state == 1 and value <= l:
            state = 0
        out.append(state)
    return pd.Series(out, index=counts.index, dtype="int8")


def t1_position_from_raw(raw_state: pd.Series) -> pd.Series:
    # risk_state=1 is Risk-off, so T+1 position is invested only when the
    # previous trading day's raw risk state was 0.
    return (1 - raw_state.shift(1).fillna(0).astype(int)).astype("int8")


def _load_source_base(ctx: D1C1Context) -> pd.DataFrame:
    path = ctx.asset_dir / "kospi_d1c1_frozen_core15_source_base.parquet"
    _require_file(path, "D1-C1 frozen Core15 source base")
    return normalize_date(pd.read_parquet(path))


def _compute_combo_from_components(
    source: pd.DataFrame,
    component_ids: list[str],
    k: int,
    l: int,
) -> pd.DataFrame:
    missing = [cid for cid in component_ids if cid not in source.columns]
    if missing:
        raise KeyError(f"component columns missing: {missing[:5]}")
    out = source[["date", *component_ids]].copy()
    valid = out[component_ids].notna().all(axis=1)
    counts = out[component_ids].fillna(0).astype("int8").sum(axis=1)
    raw = hysteresis_from_counts(counts.where(valid, 0), k, l)
    return pd.DataFrame(
        {
            "date": out["date"],
            "raw_risk_state": raw.where(valid, pd.NA).astype("Int8"),
            "on_count": counts.astype("Int16"),
            "valid_signal": valid,
        }
    )


def replay_frozen_signals(ctx: D1C1Context) -> dict[str, Any]:
    graph = build_dependency_graph(ctx)
    if graph["dependency_missing_count"]:
        return {
            "gate": "BLOCKED_KOSPI_MACRO5_D1C1A_DEPENDENCY_MISSING",
            "dependency_graph": graph,
        }

    final9 = _load_final9_dictionary(ctx)
    raw_dict = _load_stage06_raw_dictionary(ctx)
    source = _load_source_base(ctx)
    child_specs = raw_dict.set_index("combo1_id")

    expanded = source.copy()

    final_rows: list[pd.DataFrame] = []
    component_rows: list[pd.DataFrame] = []
    metrics = pd.read_csv(ctx.asset_dir / "kospi_final9_candidate_metrics.csv")
    slot_by_id = dict(zip(metrics["candidate_id"], metrics["slot"]))
    type_by_id = dict(zip(metrics["candidate_id"], metrics["model_type"]))

    for final_id, spec in final9.items():
        component_ids = list(spec["component_ids"])
        frame = _compute_combo_from_components(expanded, component_ids, int(spec["K"]), int(spec["L"]))
        frame["candidate_id"] = final_id
        frame["model_type"] = spec["model_type"]
        frame["slot"] = int(slot_by_id.get(final_id, 0))
        frame["t1_position"] = t1_position_from_raw(frame["raw_risk_state"].astype("float").fillna(0))
        final_rows.append(frame[["date", "candidate_id", "model_type", "slot", "raw_risk_state", "on_count", "t1_position"]])

        comp = expanded[["date", *component_ids]].melt(
            id_vars="date",
            var_name="component_id",
            value_name="component_risk_state",
        )
        comp["parent_candidate_id"] = final_id
        comp["parent_slot"] = int(slot_by_id.get(final_id, 0))
        comp["parent_model_type"] = type_by_id.get(final_id, spec["model_type"])
        comp["valid_signal"] = comp["component_risk_state"].notna()
        component_rows.append(comp)

    replay_final = pd.concat(final_rows, ignore_index=True)
    replay_components = pd.concat(component_rows, ignore_index=True)

    ref_final = normalize_date(pd.read_parquet(ctx.asset_dir / "kospi_final9_reference_signals.parquet"))
    ref_components = normalize_date(pd.read_parquet(ctx.asset_dir / "kospi_final9_component_reference_signals.parquet"))

    final_cmp = ref_final.merge(
        replay_final,
        on=["date", "candidate_id"],
        how="left",
        suffixes=("_ref", "_replay"),
        indicator=True,
    )
    final_mismatch = final_cmp[
        (final_cmp["_merge"] != "both")
        | (final_cmp["raw_risk_state_ref"].astype("float") != final_cmp["raw_risk_state_replay"].astype("float"))
        | (
            final_cmp["on_count_ref"].notna()
            & (final_cmp["on_count_ref"].astype("float") != final_cmp["on_count_replay"].astype("float"))
        )
        | (final_cmp["t1_position_ref"].astype("float") != final_cmp["t1_position_replay"].astype("float"))
    ].copy()

    comp_cmp = ref_components.merge(
        replay_components,
        on=["date", "parent_candidate_id", "component_id"],
        how="left",
        suffixes=("_ref", "_replay"),
        indicator=True,
    )
    comp_mismatch = comp_cmp[
        (comp_cmp["_merge"] != "both")
        | (comp_cmp["component_risk_state_ref"].astype("float") != comp_cmp["component_risk_state_replay"].astype("float"))
    ].copy()

    report_dir = ctx.report_dir
    report_dir.mkdir(exist_ok=True)
    final_mismatch_path = report_dir / "kospi_macro5_d1c1a_final_signal_mismatches.csv"
    component_mismatch_path = report_dir / "kospi_macro5_d1c1a_component_state_mismatches.csv"
    final_mismatch.head(10000).to_csv(final_mismatch_path, index=False)
    comp_mismatch.head(10000).to_csv(component_mismatch_path, index=False)

    final_mismatch_count = int(len(final_mismatch))
    component_mismatch_count = int(len(comp_mismatch))
    gate = (
        "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY"
        if final_mismatch_count == 0 and component_mismatch_count == 0
        else "BLOCKED_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_MISMATCH"
    )
    return {
        "gate": gate,
        "dependency_graph": graph,
        "core15_state_mismatch_count": component_mismatch_count,
        "combo_final_t1_mismatch_count": final_mismatch_count,
        "combo1_component_state_mismatch_count": int(
            comp_mismatch[comp_mismatch["parent_model_type_ref"].eq("combo1")].shape[0]
        )
        if len(comp_mismatch)
        else 0,
        "combo2_child_state_mismatch_count": int(
            comp_mismatch[comp_mismatch["parent_model_type_ref"].eq("combo2")].shape[0]
        )
        if len(comp_mismatch)
        else 0,
        "reference_final_rows": int(len(ref_final)),
        "replay_final_rows": int(len(replay_final)),
        "reference_component_rows": int(len(ref_components)),
        "replay_component_rows": int(len(replay_components)),
        "output_files": {
            "final_signal_mismatches": ctx.rel_dashboard(final_mismatch_path),
            "component_state_mismatches": ctx.rel_dashboard(component_mismatch_path),
        },
    }


def run_live_adapter_probe(ctx: D1C1Context) -> dict[str, Any]:
    """Probe live adapters without mutating frozen historical parity outputs.

    D1-C1 intentionally separates live freshness policy from historical replay.
    This probe records source reachability and whether a live tail can be
    appended with the current runtime contract.
    """

    statuses: list[dict[str, Any]] = []
    try:
        import yfinance as yf  # type: ignore

        df = yf.download("^KS11", period="10d", progress=False, auto_adjust=False)
        if df is not None and len(df):
            last = pd.to_datetime(df.index).max().strftime("%Y-%m-%d")
            statuses.append(
                {
                    "source_id": "kospi_ohlcv",
                    "adapter": "yfinance.download",
                    "reachable": True,
                    "rows": int(len(df)),
                    "latest_date": last,
                    "error": "",
                }
            )
        else:
            statuses.append(
                {
                    "source_id": "kospi_ohlcv",
                    "adapter": "yfinance.download",
                    "reachable": False,
                    "rows": 0,
                    "latest_date": "",
                    "error": "empty response",
                }
            )
    except Exception as exc:  # pragma: no cover - network dependent
        statuses.append(
            {
                "source_id": "kospi_ohlcv",
                "adapter": "yfinance.download",
                "reachable": False,
                "rows": 0,
                "latest_date": "",
                "error": repr(exc),
            }
        )

    required_live_bindings = [
        "kospi_ohlcv",
        "usdkrw",
        "vix",
        "vix3m",
        "us_10y_real_yield",
        "us_10y_yield",
        "us_2y_yield",
        "us_3m_yield",
        "us_baa_corp_yield",
        "us_aaa_corp_yield",
        "nfci",
    ]
    reachable_ids = {row["source_id"] for row in statuses if row["reachable"]}
    missing = [source_id for source_id in required_live_bindings if source_id not in reachable_ids]
    gate = (
        "PASS_KOSPI_MACRO5_D1C1B_LOCAL_LIVE_SMOKE_READY"
        if not missing
        else "REVIEW_KOSPI_MACRO5_D1C1B_LIVE_SOURCE_BINDINGS_INCOMPLETE"
    )
    return {
        "gate": gate,
        "live_tail_appended": False,
        "live_tail_append_reason": "C1-B source binding coverage is incomplete" if missing else "ready",
        "required_live_bindings": required_live_bindings,
        "missing_live_bindings": missing,
        "source_status": statuses,
        "live_freshness_policy_checked": False,
        "live_freshness_policy_stage": "D1-C2",
    }
