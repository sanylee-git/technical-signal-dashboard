"""Create the immutable Macro7 Live source/calendar contract from audited inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kosdaq_macro7_runtime.live_sources import source_specs_payload


RESEARCH = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kosdaq")
ASSETS = ROOT / "kosdaq_macro7_assets"
CALENDAR_SOURCE = ROOT / "kospi_macro5_assets/kospi_d1c2a2r_krx_calendar_asset.parquet"
CALENDAR_TARGET = ASSETS / "kosdaq_macro7_krx_calendar_asset.parquet"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance(path: Path, symbol: str) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256(path), "symbol": symbol}


def main() -> None:
    if not CALENDAR_TARGET.exists():
        shutil.copyfile(CALENDAR_SOURCE, CALENDAR_TARGET)
    if sha256(CALENDAR_TARGET) != sha256(CALENDAR_SOURCE):
        raise SystemExit("BLOCKED_KOSDAQ_MACRO7_D2_CALENDAR_COPY_HASH")
    market_config = RESEARCH / "configs/markets/kosdaq.yaml"
    source_config = RESEARCH / "configs/data_sources_stage1.yaml"
    frozen_manifest = RESEARCH / "data/frozen/kosdaq/snapshot_kosdaq_kq2_19961211_20260728_ae8665724e6d/data_manifest.json"
    signal_bank = RESEARCH / "src/macro_dashboard_kosdaq/signal_bank.py"
    dashboard_reference = ROOT / "kospi_macro5_runtime/live_contracts.py"
    availability_reference = ROOT / "kospi_macro5_runtime/live_availability.py"
    families = sorted({family for source in source_specs_payload() for family in source["required_by_indicator_families"]})
    sources = []
    for source in source_specs_payload():
        source = dict(source)
        source["timezone"] = "Asia/Seoul" if source["source_id"] == "kosdaq_ohlcv" else ("America/Chicago" if source["source_id"] == "nfci" else "America/New_York")
        source["calendar_or_release_basis"] = "XKRX completed session" if source["source_id"] == "kosdaq_ohlcv" else "observation_date + business-day availability lag aligned to XKRX"
        source["availability_policy"] = f"observation_date_plus_{source['lag_bdays']}_business_days"
        source["release_lag_policy"] = "nfci_weekly_friday_plus_3_bday_v1" if source["source_id"] == "nfci" else f"lag_bdays_{source['lag_bdays']}"
        source["freshness_policy"] = "completed_session_exact" if source["source_id"] == "kosdaq_ohlcv" else "latest_observation_available_under_lag_contract"
        source["fallback_policy"] = "naver_primary_yahoo_kq11_authorized_fallback" if source["source_id"] == "kosdaq_ohlcv" else "no_authorized_fallback"
        source["partial_final_policy"] = "completed_daily_only; partial is provisional and excluded from official state" if source["source_id"] == "kosdaq_ohlcv" else "provider_observation_not_a_krx_partial_close"
        source["required_raw_columns"] = ["date", "open", "high", "low", "close"] if source["source_id"] == "kosdaq_ohlcv" else ["observation_date", "value"]
        source["derived_output_columns"] = []
        sources.append(source)
    payload = {
        "contract_version": "kosdaq_macro7_live_source_contract_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "market": "KOSDAQ",
        "frozen_cutoff": "2026-07-28",
        "required_indicator_family_count": len(families),
        "required_indicator_families": families,
        "sources": sources,
        "provenance": {
            "market_config": provenance(market_config, "market.benchmark"),
            "source_config": provenance(source_config, "primary_source/fallback_source"),
            "frozen_manifest": provenance(frozen_manifest, "common_macro_lineage"),
            "signal_bank": provenance(signal_bank, "source_specs"),
            "operational_reference_live_contracts": provenance(dashboard_reference, "SOURCE_CONTRACTS; read-only provenance only"),
            "operational_reference_availability": provenance(availability_reference, "availability/derived policy; read-only provenance only"),
        },
        "runtime_dependency_policy": {
            "research_repo_runtime_import": False,
            "macro5_runtime_import": False,
            "macro5_asset_runtime_read": False,
            "calendar_asset_is_kosdaq_owned_copy": True,
            "calendar_asset_sha256": sha256(CALENDAR_TARGET),
        },
        "semantics": {
            "live_tail_date": "KRX_CALCULATION_TRADING_DATE_NOT_SOURCE_OBSERVATION_DATE",
            "source_observation_date_preserved": True,
            "frozen_prefix_authoritative_through": "2026-07-28",
            "missing_state_policy": "INVALID_NOT_RISK_ON",
            "combo2_input_semantics": "CHILD_COMBO1_RAW_RISK_STATE",
            "final_t1_application_count": 1,
            "post_gap_restart": "ONLY_IF_PINNED_ORACLE_EXPLICITLY_CONFIRMS; OTHERWISE_UNAVAILABLE",
            "current_segment_return_end_date": "candidate_basis_date",
        },
    }
    (ASSETS / "kosdaq_macro7_live_source_contract.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    calendar_contract = {
        "contract_version": "kosdaq_macro7_xkrx_calendar_v1",
        "market": "KOSDAQ",
        "exchange": "XKRX",
        "timezone": "Asia/Seoul",
        "asset_path": "kosdaq_macro7_assets/kosdaq_macro7_krx_calendar_asset.parquet",
        "asset_sha256": sha256(CALENDAR_TARGET),
        "source_lineage": "independent copied XKRX schedule asset; runtime does not read another market asset",
        "holiday_hardcoded_count": 0,
    }
    (ASSETS / "kosdaq_macro7_krx_calendar_contract.json").write_text(json.dumps(calendar_contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(sources), "families": len(families), "calendar_sha256": calendar_contract["asset_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
