from __future__ import annotations

import json
import os
import hmac
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from .cloud_probe import run_kospi_macro5_cloud_probe
from .engine import sha256_text


FIXED_AS_OF_UTC = datetime(2026, 8, 2, 7, 32, tzinfo=timezone.utc)


def handle_kospi_macro5_cloud_probe() -> bool:
    if _query_param("macro5_probe") != "1":
        return False

    expected_token = _probe_token()
    supplied_token = _query_param("macro5_probe_token")
    if not expected_token or not supplied_token or not hmac.compare_digest(str(expected_token), str(supplied_token)):
        st.error("Access denied.")
        st.stop()

    mode = (_query_param("macro5_probe_mode") or "fixed").strip().lower()
    if mode not in {"fixed", "current"}:
        st.error("Invalid probe mode.")
        st.stop()

    as_of_utc = FIXED_AS_OF_UTC if mode == "fixed" else datetime.now(timezone.utc)
    result = run_kospi_macro5_cloud_probe(as_of_utc=as_of_utc, output_path=None)
    sanitized = _sanitize_probe_result(result, run_mode=mode)

    st.title("KOSPI Macro5 Cloud Probe")
    st.json(sanitized)
    st.download_button(
        "Download probe JSON",
        data=json.dumps(sanitized, ensure_ascii=False, indent=2, default=str),
        file_name=f"kospi_macro5_cloud_probe_{mode}.json",
        mime="application/json",
    )
    st.stop()


def _query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def _probe_token() -> str:
    try:
        token = st.secrets.get("KOSPI_MACRO5_PROBE_TOKEN", "")
    except Exception:
        token = ""
    return str(token or os.environ.get("KOSPI_MACRO5_PROBE_TOKEN", ""))


def _sanitize_probe_result(result: dict[str, Any], *, run_mode: str) -> dict[str, Any]:
    safe = {
        "probe_contract_version": result.get("probe_contract_version"),
        "probe_status": result.get("probe_status"),
        "run_mode": run_mode,
        "as_of_utc": result.get("as_of_utc"),
        "as_of_kst": result.get("as_of_kst"),
        "environment_fingerprint": _sanitize_environment(result.get("environment_fingerprint", {})),
        "calendar": result.get("calendar", {}),
        "source_contract": result.get("source_contract", {}),
        "sources": [_sanitize_source(row) for row in result.get("sources", [])],
        "candidates": [_sanitize_candidate(row) for row in result.get("candidates", [])],
        "group_summary": result.get("group_summary", {}),
        "hashes": result.get("hashes", {}),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
    }
    safe["hashes"]["probe_json_canonical_hash"] = sha256_text(
        json.dumps(
            {
                "run_mode": safe["run_mode"],
                "as_of_utc": safe["as_of_utc"],
                "calendar": safe["calendar"],
                "sources": safe["sources"],
                "candidates": safe["candidates"],
                "group_summary": safe["group_summary"],
                "hashes": {
                    key: value
                    for key, value in safe["hashes"].items()
                    if key != "probe_json_canonical_hash"
                },
            },
            sort_keys=True,
            default=str,
        )
    )
    return _json_safe(safe)


def _sanitize_environment(env: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "python_version",
        "platform",
        "timezone",
        "pandas_version",
        "numpy_version",
        "pyarrow_version",
        "yfinance_version",
        "curl_cffi_version",
        "requests_version",
        "calendar_package",
        "calendar_package_version",
        "runtime_code_hash",
        "contract_hashes",
    }
    return {key: value for key, value in env.items() if key in allowed}


def _sanitize_source(row: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "source_id",
        "provider",
        "provider_series_id",
        "fetch_status",
        "freshness_status",
        "raw_latest_observation_date",
        "selected_latest_observation_date",
        "latest_available_date",
        "latest_krx_aligned_date",
        "expected_latest_observation_date",
        "expected_latest_available_date",
        "expected_latest_krx_aligned_date",
        "selected_route",
        "selected_attempt",
        "row_count",
        "tail_hash",
        "data_hash",
        "lag_krx_sessions",
    ]
    out = {field: row.get(field) for field in fields if field in row}
    out["retry_executed"] = bool(row.get("selected_attempt") not in (None, "", 1, "1"))
    out["date_regression"] = row.get("freshness_status") == "DATE_REGRESSION"
    return out


def _sanitize_candidate(row: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "candidate_id",
        "model_type",
        "role",
        "basis_date",
        "calculable",
        "freshness_qualified",
        "raw_risk_state",
        "t1_position",
        "active_count",
        "component_count",
        "K",
        "L",
        "freshness_status",
        "blocked_source_ids",
        "new_start_signal",
        "new_end_signal",
        "current_state_start_date",
        "current_state_trading_days",
    ]
    return {field: row.get(field) for field in fields if field in row}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value
