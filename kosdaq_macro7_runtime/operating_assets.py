"""Load the user-locked KOSDAQ operating set without rewriting frozen baselines."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ASSETS = Path(__file__).resolve().parents[1] / "kosdaq_macro7_assets"
OPERATING = ASSETS / "operating"


def load_operating_final_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    final_path = OPERATING / "kosdaq_macro7_final10.csv"
    definitions_path = OPERATING / "kosdaq_macro7_signal_definition_additions.csv"
    children_path = OPERATING / "kosdaq_macro7_combo2_child_mapping.csv"

    final = pd.read_csv(final_path if final_path.exists() else ASSETS / "kosdaq_macro7_final10.csv")
    definitions = pd.read_csv(ASSETS / "kosdaq_macro7_signal_definitions.csv")
    if definitions_path.exists():
        additions = pd.read_csv(definitions_path)
        if set(definitions["candidate_id"]) & set(additions["candidate_id"]):
            raise ValueError("KOSDAQ operating signal-definition additions duplicate a frozen candidate ID")
        definitions = pd.concat([definitions, additions], ignore_index=True)
    children = pd.read_csv(children_path if children_path.exists() else ASSETS / "kosdaq_macro7_combo2_child_mapping.csv")

    if final["candidate_id"].astype(str).duplicated().any():
        raise ValueError("KOSDAQ operating Final10 contains duplicate candidate IDs")
    if len(final) != 10 or final["candidate_id"].nunique() != 10:
        raise ValueError("KOSDAQ operating Final10 must contain exactly ten unique candidates")
    return final.reset_index(drop=True), definitions.reset_index(drop=True), children.reset_index(drop=True)


def load_frozen_display_states() -> pd.DataFrame:
    base = pd.read_parquet(ASSETS / "frozen/final_t1_reference.parquet")
    base_columns = ["combo_id", "date"]
    if "risk_off_t1" in base.columns:
        base_columns.append("risk_off_t1")
    base_columns.append("invest_position")
    base = base[base_columns]
    additions_path = OPERATING / "final_t1_reference_additions.parquet"
    if additions_path.exists():
        additions = pd.read_parquet(additions_path)
        required = set(base_columns)
        if not required.issubset(additions.columns):
            raise ValueError("KOSDAQ Official T+1 additions are missing required state columns")
        if set(base["combo_id"].astype(str)) & set(additions["combo_id"].astype(str)):
            raise ValueError("KOSDAQ Official T+1 additions overlap frozen candidate IDs")
        base = pd.concat([base, additions[base_columns]], ignore_index=True)
    base["date"] = pd.to_datetime(base["date"]).dt.normalize()
    return base
