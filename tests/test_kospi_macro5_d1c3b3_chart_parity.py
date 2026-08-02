from __future__ import annotations

import pandas as pd

import technical_signal_dashboard as dashboard


def _benchmark() -> pd.DataFrame:
    dates = pd.to_datetime(["2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"])
    return pd.DataFrame({"date": dates, "kospi_close": [3180, 3200, 3175, 3150, 3165, 3190]})


def _candidate_signal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": _benchmark()["date"],
            "raw_risk_state": [0, 1, 1, 0, 0, 1],
            "t1_position": [1, 1, 0, 0, 1, 1],
            "risk_start_signal": [0, 1, 0, 0, 0, 1],
            "risk_end_signal": [0, 0, 0, 1, 0, 0],
            "valid_signal": [True] * 6,
        }
    )


def _component_signal(component_id: str = "child_combo1") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": _benchmark()["date"],
            "component_id": component_id,
            "component_risk_state": [0, 1, 1, 0, 0, 1],
            "component_active_count": [1, 4, 5, 2, 1, 4],
            "component_K": [4] * 6,
            "component_L": [1] * 6,
            "component_risk_start_signal": [0, 1, 0, 0, 0, 1],
            "component_risk_end_signal": [0, 0, 0, 1, 0, 0],
            "valid_signal": [True] * 6,
        }
    )


def test_macro5_main_chart_uses_basis_date_and_macro4_height():
    fig = dashboard._macro5_kospi_build_main_chart(
        _candidate_signal(),
        _benchmark(),
        "KOSPI test",
        2,
        False,
        basis_date="2026-07-31",
    )
    assert fig is not None
    assert fig.layout.height == 300
    assert pd.to_datetime(fig.layout.xaxis.range[1]).normalize() == pd.Timestamp("2026-07-31")
    names = {trace.name for trace in fig.data}
    assert {"KOSPI", "Risk 시작", "Risk 종료"}.issubset(names)


def test_macro5_combo2_component_chart_uses_dual_axis_events_and_no_on_square():
    fig = dashboard._macro5_kospi_build_component_chart(
        _component_signal(),
        _benchmark(),
        "child combo1",
        2,
        model_type="combo2",
        basis_date="2026-07-31",
    )
    assert fig is not None
    assert fig.layout.height == 260
    assert pd.to_datetime(fig.layout.xaxis.range[1]).normalize() == pd.Timestamp("2026-07-31")
    assert fig.layout.yaxis2.overlaying == "y"
    names = {trace.name for trace in fig.data}
    assert {"ON 수", "K", "L", "KOSPI", "Risk 시작", "Risk 종료"}.issubset(names)
    assert "component ON" not in names


def test_macro5_component_chart_rejects_truncated_component_history():
    truncated = _component_signal().iloc[:-1].copy()
    fig = dashboard._macro5_kospi_build_component_chart(
        truncated,
        _benchmark(),
        "truncated",
        2,
        model_type="combo2",
        basis_date="2026-07-31",
    )
    assert fig is None


def test_macro5_normal_ui_no_technical_component_caption():
    text = (dashboard.__file__ and open(dashboard.__file__, encoding="utf-8").read())
    assert 'f"state={_macro5_kospi_state_label' not in text
    assert "reference={_component_latest5k" not in text
    assert 'st.checkbox("보조선 표시"' in text
    assert 'with st.expander(f"{_idx5k}. {_component_label5k}", expanded=True)' in text
