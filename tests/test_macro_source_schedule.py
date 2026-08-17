from __future__ import annotations

from html import unescape
from pathlib import Path

from macro_source_schedule import source_schedule_table_html


ROOT = Path(__file__).resolve().parents[1]


def test_schedule_tables_are_compact_static_guidance() -> None:
    for market, local_label in (("snp", "S&P500 기반 지표"), ("kospi", "KOSPI 파생"), ("kosdaq", "KOSDAQ 파생")):
        html = source_schedule_table_html(market)
        assert html.count("<tbody>") == 1
        assert html.count("<tr>") == 4
        assert local_label in unescape(html)
        assert "갱신 주기" in html
        assert "권장 확인 시각(KST)" in html
        assert "NFCI 신용스트레스" in html


def test_all_three_macro_pages_wire_the_existing_schedule_expander() -> None:
    dashboard = (ROOT / "technical_signal_dashboard.py").read_text(encoding="utf-8")
    kosdaq_ui = (ROOT / "kosdaq_macro7_ui.py").read_text(encoding="utf-8")

    assert 'source_schedule_table_html("snp")' in dashboard
    assert 'source_schedule_table_html("kospi")' in dashboard
    assert 'source_schedule_table_html("kosdaq")' in kosdaq_ui
