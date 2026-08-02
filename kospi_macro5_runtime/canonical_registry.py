from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


CANONICAL_GROUPS: dict[str, dict[str, Any]] = {
    "canonical_kospi_ohlc": {
        "source_ids": ["kospi_ohlcv"],
        "consumers": ["kospi_index_level", "kospi_rsi", "kospi_bollinger", "kospi_natr", "kospi_hv"],
    },
    "canonical_dgs10": {
        "source_ids": ["us_10y_yield"],
        "consumers": ["us_10y_yield", "us_10y_2y_spread", "us_10y_3m_spread", "us_10y_slope", "us_hy_oas_level", "us_ig_oas_level"],
    },
    "canonical_vix": {
        "source_ids": ["vix"],
        "consumers": ["vix_level", "vix_spread", "global_credit_stress"],
    },
}


def _hash_frame(frame: pd.DataFrame, cols: list[str]) -> str:
    if frame is None or frame.empty:
        return ""
    use = frame[[c for c in cols if c in frame.columns]].copy()
    if "observation_date" in use:
        use["observation_date"] = pd.to_datetime(use["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    text = use.sort_values([c for c in ["source_id", "observation_date"] if c in use.columns]).tail(256).to_csv(index=False)
    return hashlib.sha256(text.encode()).hexdigest()


def build_canonical_registry(provider_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, object]] = []
    consumers: list[dict[str, object]] = []
    for canonical_id, spec in CANONICAL_GROUPS.items():
        for source_id in spec["source_ids"]:
            frame = provider_frames.get(source_id, pd.DataFrame())
            valid = frame.loc[frame.get("valid", pd.Series(False, index=frame.index)).astype(bool)].copy() if not frame.empty else pd.DataFrame()
            latest = pd.to_datetime(valid["observation_date"], errors="coerce").max() if not valid.empty else pd.NaT
            data_hash = _hash_frame(valid, ["source_id", "observation_date", "value", "open", "high", "low", "close"])
            source_instance_id = hashlib.sha256(f"{canonical_id}|{source_id}|{data_hash}".encode()).hexdigest()[:16] if data_hash else ""
            records.append(
                {
                    "canonical_source_id": canonical_id,
                    "source_id": source_id,
                    "source_instance_id": source_instance_id,
                    "data_hash": data_hash,
                    "tail_hash": data_hash,
                    "row_count": int(len(valid)),
                    "first_date": None if valid.empty else pd.to_datetime(valid["observation_date"]).min().strftime("%Y-%m-%d"),
                    "latest_date": None if pd.isna(latest) else pd.Timestamp(latest).strftime("%Y-%m-%d"),
                    "selected_route": frame["source_route"].iloc[0] if not frame.empty and "source_route" in frame else "",
                    "fetched_at_utc": frame["fetched_at_utc"].iloc[0] if not frame.empty and "fetched_at_utc" in frame else "",
                }
            )
            for consumer in spec["consumers"]:
                consumers.append(
                    {
                        "canonical_source_id": canonical_id,
                        "consumer_id": consumer,
                        "source_id": source_id,
                        "source_instance_id": source_instance_id,
                        "data_hash": data_hash,
                        "latest_date": None if pd.isna(latest) else pd.Timestamp(latest).strftime("%Y-%m-%d"),
                        "row_count": int(len(valid)),
                        "selected_route": frame["source_route"].iloc[0] if not frame.empty and "source_route" in frame else "",
                    }
                )
    return pd.DataFrame(records), pd.DataFrame(consumers)


def consistency_from_registry(consumers: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for canonical_id, group in consumers.groupby("canonical_source_id", sort=False):
        expected_count = len(CANONICAL_GROUPS[canonical_id]["consumers"])
        bound = group.loc[group["data_hash"].astype(str).ne("")]
        unique_hash_count = int(bound["data_hash"].nunique())
        unique_instance_count = int(bound["source_instance_id"].nunique())
        empty_group = len(group) == 0 or len(bound) == 0
        consumer_binding_count = int(group["consumer_id"].nunique())
        vacuous = empty_group or consumer_binding_count < 2 or consumer_binding_count < expected_count
        status = "PASS"
        blocking = False
        if vacuous:
            status = "NOT_EVALUATED_INSUFFICIENT_CONSUMER_BINDING"
            blocking = True
        elif unique_hash_count != 1 or unique_instance_count != 1:
            status = "SOURCE_CONSISTENCY_MISMATCH"
            blocking = True
        rows.append(
            {
                "rule_id": canonical_id,
                "source_ids": "|".join(sorted(set(group["source_id"].astype(str)))) if len(group) else "",
                "consumer_count": consumer_binding_count,
                "expected_consumer_count": expected_count,
                "data_hash_unique_count": unique_hash_count,
                "source_instance_unique_count": unique_instance_count,
                "consistency_status": status,
                "blocking": blocking,
                "vacuous_pass": False,
            }
        )
    return pd.DataFrame(rows)
