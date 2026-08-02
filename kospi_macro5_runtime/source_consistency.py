from __future__ import annotations

import pandas as pd


def build_source_consistency(source_freshness: pd.DataFrame) -> pd.DataFrame:
    latest = dict(zip(source_freshness["source_id"], source_freshness["actual_latest_observation_date"]))
    rules = [
        ("kospi_canonical", ["kospi_ohlcv"], "KOSPI Index/RSI/BB/NATR/HV use one canonical OHLC frame"),
        ("vix_canonical", ["vix"], "VIX level, VIX spread, and credit stress share canonical VIX frame"),
        ("dgs10_canonical", ["us_10y_yield"], "10Y, spreads, slope, HY proxy, and IG proxy share canonical DGS10 frame"),
        ("hy_proxy_inputs", ["us_baa_corp_yield", "us_10y_yield"], "HY proxy constituent latest dates recorded"),
        ("ig_proxy_inputs", ["us_aaa_corp_yield", "us_10y_yield"], "IG proxy constituent latest dates recorded"),
    ]
    rows = []
    for rule_id, sources, note in rules:
        dates = [latest.get(sid) for sid in sources if latest.get(sid)]
        mismatch = len(set(dates)) > 1 if len(dates) == len(sources) else False
        rows.append(
            {
                "rule_id": rule_id,
                "source_ids": "|".join(sources),
                "latest_dates": "|".join(str(x) for x in dates),
                "consistency_status": "SOURCE_CONSISTENCY_MISMATCH" if mismatch else "PASS",
                "blocking": bool(mismatch and rule_id in {"kospi_canonical", "vix_canonical", "dgs10_canonical"}),
                "notes": note,
            }
        )
    return pd.DataFrame(rows)


def blocking_source_ids(consistency: pd.DataFrame) -> set[str]:
    blocked: set[str] = set()
    if consistency.empty:
        return blocked
    for row in consistency.loc[consistency["blocking"].astype(bool)].itertuples(index=False):
        blocked.update(str(row.source_ids).split("|"))
    return blocked
