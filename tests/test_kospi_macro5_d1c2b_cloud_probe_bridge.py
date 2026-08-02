from __future__ import annotations

from kospi_macro5_runtime.streamlit_cloud_probe_bridge import FIXED_AS_OF_UTC, _sanitize_probe_result


def test_fixed_probe_as_of_contract():
    assert FIXED_AS_OF_UTC.isoformat() == "2026-08-02T07:32:00+00:00"


def test_probe_sanitizer_does_not_emit_token_or_raw_paths():
    result = {
        "probe_contract_version": "d1c2b_streamlit_cloud_probe_v1",
        "probe_status": "FULL_CLOUD_PROBE_EXECUTED",
        "as_of_utc": "2026-08-02T07:32:00+00:00",
        "as_of_kst": "2026-08-02T16:32:00+09:00",
        "environment_fingerprint": {
            "python_version": "3.x",
            "platform": "test-platform",
            "timezone": "KST",
            "runtime_code_hash": "abc",
            "HOME": "/Users/someone",
            "KOSPI_MACRO5_PROBE_TOKEN": "secret",
        },
        "calendar": {"latest_completed_session": "2026-07-31"},
        "source_contract": {"source_count": 11},
        "sources": [
            {
                "source_id": "kospi_ohlcv",
                "provider": "pykrx",
                "fetch_status": "IMPLEMENTED_FETCH_OK",
                "freshness_status": "FRESH",
                "data_hash": "hash",
                "raw_history": [1, 2, 3],
            }
        ],
        "candidates": [
            {
                "candidate_id": "candidate",
                "raw_risk_state": 1,
                "t1_position": 0,
                "token": "secret",
            }
        ],
        "group_summary": {},
        "hashes": {"candidate_semantic_hash": "candidate-hash"},
        "errors": [],
        "warnings": [],
    }

    safe = _sanitize_probe_result(result, run_mode="fixed")
    text = str(safe)
    assert "secret" not in text
    assert "/Users/someone" not in text
    assert "raw_history" not in text
    assert safe["sources"][0]["source_id"] == "kospi_ohlcv"
    assert safe["candidates"][0]["candidate_id"] == "candidate"
    assert "probe_json_canonical_hash" in safe["hashes"]
