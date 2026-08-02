from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_page_adapter_is_not_probe_or_streamlit_bridge():
    text = (ROOT / "kospi_macro5_runtime/page_adapter.py").read_text()
    forbidden = [
        "streamlit",
        "streamlit_cloud_probe_bridge",
        "run_kospi_macro5_cloud_probe",
        "KOSPI_MACRO5_PROBE_TOKEN",
        "query_params",
        "last_known_good",
    ]
    for needle in forbidden:
        assert needle not in text


def test_macro5_live_loader_is_lazy_and_macro5_scoped():
    text = (ROOT / "technical_signal_dashboard.py").read_text()
    assert "def _load_macro5_kospi_live_page_data_cached" in text
    assert "from kospi_macro5_runtime.page_adapter import load_macro5_live_page_data" in text
    assert text.count("_load_macro5_kospi_live_page_data_cached(") == 2
    render_pos = text.index("def render_macro5_kospi_section")
    call_pos = text.index("_load_macro5_kospi_live_page_data_cached(_live_sync_bucket5k)")
    assert call_pos > render_pos


def test_probe_hook_is_not_modified_for_page_wiring():
    text = (ROOT / "technical_signal_dashboard.py").read_text()
    assert text.count('st.query_params.get("macro5_probe")') == 1
    assert text.count("streamlit_cloud_probe_bridge") == 1
