from __future__ import annotations

import pandas as pd

from kosdaq_macro7_ui import _component_status_table as kosdaq_component_status_table
from kosdaq_macro7_ui import _current_status_html as kosdaq_current_status_html
from nasdaq_macro8_ui import _component_status_table as nasdaq_component_status_table
from nasdaq_macro8_ui import _current_status_html as nasdaq_current_status_html
from spx_macro9_ui import _component_status_table as spx_component_status_table
from spx_macro9_ui import _current_status_html as spx_current_status_html
from technical_signal_dashboard import _macro5_kospi_current_status_html, _macro_compact_status_html


def _status_row(basis_date: str) -> pd.Series:
    return pd.Series(
        {
            "status": "USABLE",
            "basis_date": basis_date,
            "raw_risk_state": False,
            "active_count": 1,
            "K": 3,
            "invest_position": 1,
            "current_risk_start_date": "2026-09-04",
            "current_duration_trading_days": 3,
            "current_segment_return": 0.01,
            "risk_start": False,
            "risk_end": False,
        }
    )


def _component_payload() -> dict:
    return {
        "component_history": pd.DataFrame(
            [
                {
                    "parent_candidate_id": "candidate",
                    "component_id": "component",
                    "component_order": 1,
                    "component_label": "예시 지표",
                    "component_valid": True,
                    "component_risk_state": False,
                    "date": "2026-09-08",
                }
            ]
        ),
        "component_confirmed_basis_by_id": {"component": "2026-09-04"},
        "confirmed_basis_by_candidate": {"candidate": "2026-09-04"},
    }


def test_all_independent_tabs_render_gap_on_provisional_line() -> None:
    history = pd.DataFrame(
        {
            "date": ["2026-09-04", "2026-09-07", "2026-09-08"],
            "risk_start": [False, False, False],
            "risk_end": [False, False, False],
        }
    )
    confirmed = _status_row("2026-09-04")
    provisional = _status_row("2026-09-08")

    renderers = (
        kosdaq_current_status_html,
        nasdaq_current_status_html,
        spx_current_status_html,
    )
    for renderer in renderers:
        html = renderer(provisional, history, confirmed)
        assert "잠정신호:" in html
        assert "· 확정 기준과 2 거래일 차이" in html
        assert "확정 기준과 2 거래일 차이</span><br>" in html
        assert "<br><span style='color:rgba(255,255,255,.56)'>확정 기준" not in html


def test_component_tables_show_confirmed_basis_for_provisional_date() -> None:
    payload = _component_payload()
    for renderer in (
        kosdaq_component_status_table,
        nasdaq_component_status_table,
        spx_component_status_table,
    ):
        html = renderer(payload, "candidate")
        assert "2026-09-08 · 잠정 · 확정 2026-09-04" in html


def test_shared_status_renderer_keeps_gap_inline() -> None:
    html = _macro_compact_status_html(
        basis_date="2026-09-08",
        active_count=2,
        component_count=5,
        risk_state=1,
        execution_position=0,
        start_event=False,
        end_event=False,
        state_start="2026-09-04",
        duration_text="3",
        confirmed_snapshot={"basis_date": "2026-09-04", "active_count": 2, "raw_risk_state": 1, "calculable": True},
        confirmed_gap=2,
    )
    assert "잠정신호:" in html
    assert "확정 기준과 2 거래일 차이" in html


def test_kospi_status_renderer_calculates_session_gap_from_existing_history() -> None:
    html = _macro5_kospi_current_status_html(
        pd.Series({"K": 3, "L": 1}),
        {
            "basis_date": "2026-09-08",
            "active_count": 2,
            "raw_risk_state": 1,
            "t1_position": 0,
            "new_start_signal": False,
            "new_end_signal": False,
            "current_state_start_date": "2026-09-04",
            "current_state_trading_days": 3,
        },
        5,
        True,
        benchmark_history=pd.DataFrame(
            {"date": ["2026-09-04", "2026-09-07", "2026-09-08"], "kospi_close": [100, 99, 98]}
        ),
        confirmed_live_row={"basis_date": "2026-09-04", "active_count": 2, "raw_risk_state": 1, "calculable": True},
    )
    assert "잠정신호:" in html
    assert "확정 기준과 2 거래일 차이" in html
