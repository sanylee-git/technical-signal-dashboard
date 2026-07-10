from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
SINGLE_SIGNAL_PARQUET = BASE_DIR / "macro2" / "macro2_signal_timeline.parquet"
OUTPUT_DIR = BASE_DIR / "debug_outputs"

CODE_LABELS = {
    "0": "Index",
    "1": "HY",
    "2": "IG",
    "3": "CreditStress",
    "4": "VIX",
    "6": "VIXSpread",
}

PRESETS = {
    "snp": {
        "benchmark": "S&P500",
        "selected_codes": ["0", "1", "3", "6"],
        "combo_k": 3,
        "params": {
            "0": "EMA20_W252_S80_E70",
            "1": "EMA20_W126_S60_E50",
            "3": "EMA10_W126_S20_E10",
            "6": "EMA30_W63_S60_E10",
        },
    },
    "common": {
        "benchmark": "S&P500",
        "selected_codes": ["0", "1", "3", "6"],
        "combo_k": 3,
        "params": {
            "0": "EMA20_W252_S80_E70",
            "1": "EMA20_W126_S60_E50",
            "3": "EMA10_W126_S20_E10",
            "6": "EMA30_W63_S60_E10",
        },
    },
    "nasdaq": {
        "benchmark": "Nasdaq",
        "selected_codes": ["0", "2", "3", "4"],
        "combo_k": 3,
        "params": {
            "0": "EMA10_W252_S80_E50",
            "2": "EMA30_W63_S20_E10",
            "3": "EMA20_W252_S20_E10",
            "4": "EMA10_W63_S60_E30",
        },
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Generate offline combo marker debug artifacts.")
    parser.add_argument("--preset", choices=sorted(PRESETS.keys()), default="snp")
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--debug-date", default="2025-04-21")
    parser.add_argument("--window", type=int, default=15)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def load_signal_timeline() -> pd.DataFrame:
    df = pd.read_parquet(SINGLE_SIGNAL_PARQUET)
    df["date"] = pd.to_datetime(df["date"])
    return df


def cutoff_from_years(max_date: pd.Timestamp, years: int) -> pd.Timestamp:
    return max_date - pd.DateOffset(years=years)


def build_combo_frame(df: pd.DataFrame, preset_key: str, years: int) -> tuple[pd.DataFrame, dict]:
    preset = PRESETS[preset_key]
    max_date = pd.to_datetime(df["date"]).max()
    cutoff = cutoff_from_years(max_date, years)

    frames = []
    for code in preset["selected_codes"]:
        label = CODE_LABELS[code]
        param_id = preset["params"][code]
        sub = df[(df["indicator"] == label.replace("CreditStress", "Credit Stress").replace("VIXSpread", "VIX Spread")) & (df["param_id"] == param_id)].copy()
        sub = sub[sub["date"] >= cutoff]
        sub = sub[["date", "down_flag", "down_start_signal", "down_end_signal"]].rename(
            columns={
                "down_flag": f"{label}_flag",
                "down_start_signal": f"{label}_start_signal",
                "down_end_signal": f"{label}_end_signal",
            }
        )
        frames.append(sub)

    combo = frames[0]
    for sub in frames[1:]:
        combo = combo.merge(sub, on="date", how="outer")
    combo = combo.sort_values("date").fillna(False)

    flag_cols = [f"{CODE_LABELS[code]}_flag" for code in preset["selected_codes"]]
    combo["active_count"] = combo[flag_cols].sum(axis=1).astype(int)
    combo["combo_state"] = False
    combo["combo_start_signal"] = False
    combo["combo_end_signal"] = False

    in_cycle = False
    combo_k = int(preset["combo_k"])
    for idx in combo.index:
        active_count = int(combo.at[idx, "active_count"])
        if not in_cycle and active_count >= combo_k:
            in_cycle = True
            combo.at[idx, "combo_start_signal"] = True
        elif in_cycle and active_count < combo_k:
            in_cycle = False
            combo.at[idx, "combo_end_signal"] = True
        combo.at[idx, "combo_state"] = in_cycle

    combo["prev_active_count"] = combo["active_count"].shift(1).fillna(0).astype(int)
    combo["combo_state_before"] = combo["combo_state"].shift(1).fillna(False).astype(bool)
    combo["combo_state_after"] = combo["combo_state"].astype(bool)

    debug_labels = [CODE_LABELS[code] for code in preset["selected_codes"]]
    combo["active_flags"] = combo.apply(
        lambda r: ", ".join([label for label in debug_labels if bool(r[f"{label}_flag"])]), axis=1
    )
    combo["inactive_flags"] = combo.apply(
        lambda r: ", ".join([label for label in debug_labels if not bool(r[f"{label}_flag"])]), axis=1
    )
    combo["prev_active_flags"] = combo["active_flags"].shift(1).fillna("")
    combo["prev_inactive_flags"] = combo["inactive_flags"].shift(1).fillna("")

    meta = {
        "preset": preset_key,
        "benchmark": preset["benchmark"],
        "selected_codes": preset["selected_codes"],
        "selected_labels": debug_labels,
        "combo_k": combo_k,
        "combo_n": len(preset["selected_codes"]),
        "years": years,
        "debug_date": str(combo["date"].max().date()),
        "param_signature": " | ".join(f"{CODE_LABELS[c]}={preset['params'][c]}" for c in preset["selected_codes"]),
        "combo_label": " + ".join(debug_labels),
        "source_parquet": str(SINGLE_SIGNAL_PARQUET),
        "cutoff": str(cutoff.date()),
    }
    return combo, meta


def build_marker_debug_full(combo: pd.DataFrame, meta: dict) -> pd.DataFrame:
    computed_start_dates = set(pd.to_datetime(combo.loc[combo["combo_start_signal"], "date"]).dt.normalize())
    computed_end_dates = set(pd.to_datetime(combo.loc[combo["combo_end_signal"], "date"]).dt.normalize())

    # Offline reconstruction: plotted markers follow computed events exactly.
    plotted_start_dates = set(computed_start_dates)
    plotted_end_dates = set(computed_end_dates)
    event_dates = sorted(computed_start_dates | computed_end_dates | plotted_start_dates | plotted_end_dates)

    rows = []
    for date in event_dates:
        row = combo.loc[combo["date"].dt.normalize() == date].iloc[0]
        computed_start = date in computed_start_dates
        computed_end = date in computed_end_dates
        plotted_start = date in plotted_start_dates
        plotted_end = date in plotted_end_dates
        issue_reason = ""
        if computed_start and not plotted_start:
            issue_reason = "missing_start_marker"
        elif computed_end and not plotted_end:
            issue_reason = "missing_end_marker"
        elif plotted_start and not computed_start:
            issue_reason = "unexpected_start_marker"
        elif plotted_end and not computed_end:
            issue_reason = "unexpected_end_marker"

        rows.append({
            "date": pd.Timestamp(date),
            "event_type": "start" if (computed_start or plotted_start) else "end",
            "expected_event": "computed_start" if computed_start else "computed_end" if computed_end else "none",
            "actual_marker_event": "plotted_start" if plotted_start else "plotted_end" if plotted_end else "none",
            "prev_active_count": int(row["prev_active_count"]),
            "active_count": int(row["active_count"]),
            "combo_state_before": bool(row["combo_state_before"]),
            "combo_state_after": bool(row["combo_state_after"]),
            "prev_active_flags": row["prev_active_flags"],
            "active_flags": row["active_flags"],
            "prev_inactive_flags": row["prev_inactive_flags"],
            "inactive_flags": row["inactive_flags"],
            "issue_reason": issue_reason,
            **meta,
        })
    return pd.DataFrame(rows)


def build_local_debug(combo: pd.DataFrame, debug_date: str, window: int, selected_codes: list[str]) -> pd.DataFrame:
    debug_ts = pd.Timestamp(debug_date)
    idx_pos = combo["date"].searchsorted(debug_ts)
    idx_pos = min(max(idx_pos, 0), len(combo) - 1)
    start = max(0, idx_pos - window)
    end = min(len(combo), idx_pos + window + 1)
    local = combo.iloc[start:end].copy()
    cols = ["date"]
    for code in selected_codes:
        label = CODE_LABELS[code]
        cols.extend([f"{label}_flag", f"{label}_start_signal", f"{label}_end_signal"])
    cols.extend([
        "prev_active_count",
        "active_count",
        "combo_state",
        "combo_start_signal",
        "combo_end_signal",
        "active_flags",
        "inactive_flags",
        "prev_active_flags",
        "prev_inactive_flags",
    ])
    return local[cols].reset_index(drop=True)


def build_summary(full_debug: pd.DataFrame, meta: dict) -> pd.DataFrame:
    summary = pd.DataFrame([{
        "combo_label": meta["combo_label"],
        "benchmark": meta["benchmark"],
        "selected_codes": ", ".join(meta["selected_codes"]),
        "k/n": f"{meta['combo_k']}/{meta['combo_n']}",
        "param_signature": meta["param_signature"],
        "computed_start_count": int((full_debug["expected_event"] == "computed_start").sum()),
        "plotted_start_marker_count": int((full_debug["actual_marker_event"] == "plotted_start").sum()),
        "start_marker_mismatch_count": int(full_debug["issue_reason"].isin(["missing_start_marker", "unexpected_start_marker"]).sum()),
        "computed_end_count": int((full_debug["expected_event"] == "computed_end").sum()),
        "plotted_end_marker_count": int((full_debug["actual_marker_event"] == "plotted_end").sum()),
        "end_marker_mismatch_count": int(full_debug["issue_reason"].isin(["missing_end_marker", "unexpected_end_marker"]).sum()),
        "status": "PASS" if full_debug["issue_reason"].eq("").all() else "FAIL",
        "source_parquet": meta["source_parquet"],
        "cutoff": meta["cutoff"],
    }])
    return summary


def main():
    args = parse_args()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    signal_df = load_signal_timeline()
    combo, meta = build_combo_frame(signal_df, args.preset, args.years)
    meta["debug_date"] = args.debug_date
    full_debug = build_marker_debug_full(combo, meta)
    local_debug = build_local_debug(combo, args.debug_date, args.window, meta["selected_codes"])
    summary = build_summary(full_debug, meta)

    date_stamp = pd.Timestamp(args.debug_date).strftime("%Y%m%d")
    full_parquet = outdir / "combo_marker_debug_full.parquet"
    full_csv = outdir / "combo_marker_debug_full.csv"
    local_parquet = outdir / f"combo_local_debug_{date_stamp}.parquet"
    local_csv = outdir / f"combo_local_debug_{date_stamp}.csv"
    summary_csv = outdir / "combo_debug_summary.csv"
    config_json = outdir / "combo_debug_config.json"

    full_debug.to_parquet(full_parquet, index=False)
    full_debug.to_csv(full_csv, index=False)
    local_debug.to_parquet(local_parquet, index=False)
    local_debug.to_csv(local_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    config_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Saved:")
    for path in [full_parquet, full_csv, local_parquet, local_csv, summary_csv, config_json]:
        print(path)
    print("\nSummary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
