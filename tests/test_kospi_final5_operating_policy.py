from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard_role_aware_market_stage import load_role_metadata, validate_market_metadata
from dashboard_role_aware_stage import classify_role_combo
from kospi_macro5_runtime.page_adapter import _role_aware_outputs
from kospi_macro5_runtime.live_engine import _candidate_state_source, combo_from_components_nullable
from technical_signal_dashboard import (
    _macro5_kospi_build_backtest_panel,
    _macro5_kospi_combo2_main_candidate_id,
)


ASSETS = ROOT / "kospi_macro5_assets"
EXPECTED = {
    "combo1": [
        ("combo1_n11_k8_l5_93919287424179bd", 11, 8, 5, "MAIN", "균형형", None, "M"),
        ("combo1_n11_k9_l5_b984a8e53ad69a2d", 11, 9, 5, "CONFIRM", "보수방어형", "추세지속형", "H"),
        ("combo1_n11_k9_l6_ad654f06d0d609cb", 11, 9, 6, "CONFIRM", "균형형", "민감감지형", "M"),
        ("combo1_n11_k9_l6_9f0105582a0f0745", 11, 9, 6, "CONFIRM", "공격진입형", "추세지속형", "H"),
        ("combo1_n11_k8_l5_78b918eadc42fa16", 11, 8, 5, "CONFIRM", "보수방어형", "추세지속형", "H"),
    ],
    "combo2": [
        ("m10::combo2_m10_k7_l4_bbd8c760d49b44bb", 10, 7, 4, "MAIN", "균형형", None, "M"),
        ("m8::combo2_m8_k5_l4_cee6978af4789711", 8, 5, 4, "CONFIRM", "균형형", "추세지속형", "H"),
        ("m6::combo2_m6_k4_l2_2d90a80e824f7336", 6, 4, 2, "CONFIRM", "보수방어형", "추세지속형", "H"),
        ("m6::combo2_m6_k4_l3_f976de57b8b4a80e", 6, 4, 3, "CONFIRM", "공격진입형", "추세지속형", "H"),
        ("m5::combo2_m5_k2_l1_2bc7e194fdecfd9e", 5, 2, 1, "CONFIRM", "보수방어형", None, "E"),
    ],
}


def _operating_dictionary() -> dict:
    return json.loads((ASSETS / "kospi_final5_operating_dictionary.json").read_text())


def test_final5_operating_dictionary_exactly_matches_confirmed_contract() -> None:
    document = _operating_dictionary()
    actual = {"combo1": [], "combo2": []}
    role_metadata = load_role_metadata()["markets"]["KOSPI"]
    metadata_by_id = {
        str(row["candidate_id"]): (family, row)
        for family in ("COMBO1", "COMBO2")
        for row in role_metadata[family]
    }
    for candidate in document["candidates"]:
        family = candidate["model_type"]
        assert len(candidate["component_ids"]) == int(candidate["N_or_M"])
        assert len(set(candidate["component_ids"])) == int(candidate["N_or_M"])
        metadata_family, role = metadata_by_id[candidate["candidate_id"]]
        classification = classify_role_combo(role["role_1"], role.get("role_2"))
        expected = next(
            row for row in EXPECTED[family] if row[0] == candidate["candidate_id"]
        )
        assert metadata_family.lower() == family
        assert (candidate["N_or_M"], candidate["K"], candidate["L"]) == expected[1:4]
        if candidate["candidate_id"] == "combo1_n11_k8_l5_78b918eadc42fa16":
            assert candidate["state_start_date"] == "2008-04-01"
        assert (role["designation"], role["role_1"], role.get("role_2"), classification.warning_class) == expected[4:]
        actual[family].append(candidate["candidate_id"])
    assert actual == {family: [row[0] for row in rows] for family, rows in EXPECTED.items()}


def test_candidate_state_start_date_resets_only_candidate_history_prefix() -> None:
    source = pd.DataFrame(
        {
            "date": pd.to_datetime(["2008-03-31", "2008-04-01", "2008-04-02", "2008-04-03"]),
            "a": [1, 0, 0, 1],
            "b": [1, 0, 0, 1],
        }
    )
    selected = _candidate_state_source(source, {"state_start_date": "2008-04-01"})
    replay = combo_from_components_nullable(selected, ["a", "b"], 2, 0)
    assert selected["date"].min() == pd.Timestamp("2008-04-01")
    assert replay["raw_risk_state"].tolist() == [0, 0, 1]
    assert len(_candidate_state_source(source, {})) == len(source)


def test_kospi_role_metadata_validates_five_plus_five_with_one_main_each() -> None:
    operating = pd.DataFrame(
        [
            {"candidate_id": row["candidate_id"], "model_family": row["model_type"].upper()}
            for row in _operating_dictionary()["candidates"]
        ]
    )
    checks = validate_market_metadata("KOSPI", operating)
    assert len(checks) == 2
    assert all(row["status"] == "PASS" for row in checks)
    assert all((row["operational_candidates"], row["main_count"], row["confirm_count"]) == (5, 1, 4) for row in checks)
    classes = {
        family: [
            classify_role_combo(row["role_1"], row.get("role_2")).warning_class
            for row in load_role_metadata()["markets"]["KOSPI"][family]
        ]
        for family in ("COMBO1", "COMBO2")
    }
    assert {key: {value: values.count(value) for value in ("E", "M", "H")} for key, values in classes.items()} == {
        "COMBO1": {"E": 0, "M": 2, "H": 3},
        "COMBO2": {"E": 1, "M": 1, "H": 3},
    }


def test_kospi_combo2_main_selection_uses_row_position_not_index_label() -> None:
    main_id = EXPECTED["combo2"][0][0]
    metrics = pd.DataFrame(
        [{"candidate_id": main_id, "model_type": "combo2"}],
        index=[7],
    )
    assert _macro5_kospi_combo2_main_candidate_id(metrics) == main_id


def test_kospi_backtest_panel_accepts_series_from_offset_history_selector() -> None:
    candidate_id = EXPECTED["combo1"][0][0]
    dates = pd.bdate_range("2026-08-01", periods=30)
    history = pd.DataFrame(
        {
            "candidate_id": candidate_id,
            "date": dates,
            "raw_risk_state": [int(i % 4 == 0) for i in range(len(dates))],
            "active_count": [8] * len(dates),
            "on_count": [8] * len(dates),
            "valid_signal": [True] * len(dates),
        }
    )
    live_row = {
        "candidate_id": candidate_id,
        "calculable": True,
        "basis_date": dates[-1],
        "raw_risk_state": 1,
        "active_count": 8,
        "K": 8,
        "L": 5,
    }
    metrics = pd.DataFrame(
        [{
            "candidate_id": candidate_id,
            "model_type": "combo1",
            "slot": 1,
            "K": 8,
            "L": 5,
            "m_or_n": 11,
        }]
    )
    html = _macro5_kospi_build_backtest_panel(
        metrics,
        {candidate_id: live_row},
        candidate_id,
        "combo1",
        backtest_stats={},
        candidate_history=history,
        official_live_row_map={candidate_id: live_row},
    )
    assert "[조합1] Main · 균형형" in html
    assert "1개월 전" in html


def test_official_t1_four_timepoints_are_exactly_once_and_role_outputs_complete() -> None:
    operating = _operating_dictionary()
    dates = pd.bdate_range("2026-08-01", periods=45)
    history_rows = []
    snapshot_rows = []
    for candidate in operating["candidates"]:
        cid = candidate["candidate_id"]
        raw = [int((i // 7 + len(cid)) % 3 == 0) for i in range(len(dates))]
        counts = [candidate["K"] if value else 0 for value in raw]
        for i, date in enumerate(dates):
            history_rows.append(
                {
                    "candidate_id": cid,
                    "date": date,
                    "raw_risk_state": raw[i],
                    "on_count": counts[i],
                    "active_count": counts[i],
                    "t1_position": pd.NA if i == 0 else 1 - raw[i - 1],
                    "t1_valid": i > 0,
                    "valid_signal": True,
                }
            )
        snapshot_rows.append(
            {
                "candidate_id": cid,
                "model_type": candidate["model_type"],
                "basis_date": dates[-1],
                "calculable": True,
                "freshness_qualified": True,
                "raw_risk_state": raw[-1],
                "active_count": counts[-1],
                "t1_position": 1 - raw[-2],
                "t1_valid": True,
                "valid_signal": True,
                "K": candidate["K"],
                "L": candidate["L"],
            }
        )
    official, snapshot, individual, stages, red_contract = _role_aware_outputs(
        pd.DataFrame(snapshot_rows), pd.DataFrame(history_rows), operating
    )
    assert len(individual) == 40
    assert len(stages) == 12
    assert len(red_contract) == 8
    assert individual["state_status"].eq("PASS").all()
    assert red_contract["red_contract_violation"].sum() == 0
    assert snapshot["raw_risk_state"].notna().all()
    assert not official.groupby("candidate_id", sort=False)["t1_valid"].first().any()
    assert official.groupby("candidate_id", sort=False)["t1_valid"].apply(lambda values: values.iloc[1:].all()).all()
    assert all(row["state_status"] == "PASS" for row in stages)
    assert {row["timepoint_code"] for row in stages} == {"21TD", "10TD", "5TD", "TODAY"}


def test_unavailable_role_stage_is_reported_without_aborting_live_result() -> None:
    operating = _operating_dictionary()
    dates = pd.bdate_range("2026-08-01", periods=30)
    history_rows = []
    snapshot_rows = []
    for candidate in operating["candidates"]:
        cid = candidate["candidate_id"]
        raw = [0] * len(dates)
        for i, date in enumerate(dates):
            history_rows.append(
                {
                    "candidate_id": cid,
                    "date": date,
                    "raw_risk_state": raw[i],
                    "on_count": 0,
                    "active_count": 0,
                    "t1_position": pd.NA if i == 0 else 1,
                    "t1_valid": i > 0,
                    "valid_signal": True,
                }
            )
        snapshot_rows.append(
            {
                "candidate_id": cid,
                "model_type": candidate["model_type"],
                "basis_date": dates[-1],
                "calculable": True,
                "freshness_qualified": True,
                "raw_risk_state": 0,
                "active_count": 0,
                "t1_position": 1,
                "t1_valid": True,
                "valid_signal": True,
                "K": candidate["K"],
                "L": candidate["L"],
            }
        )
    snapshot = pd.DataFrame(snapshot_rows)
    snapshot.loc[snapshot["candidate_id"].eq(EXPECTED["combo1"][0][0]), "freshness_qualified"] = False

    _official, _snapshot, _individual, stages, red_contract = _role_aware_outputs(
        snapshot, pd.DataFrame(history_rows), operating
    )

    combo1_qa = red_contract.loc[red_contract["combo"].eq("COMBO1")]
    combo2_qa = red_contract.loc[red_contract["combo"].eq("COMBO2")]
    unavailable_combo1 = combo1_qa["status"].eq("UNAVAILABLE")
    assert unavailable_combo1.sum() == 2
    assert combo1_qa.loc[unavailable_combo1, "red_contract_violation"].isna().all()
    assert combo1_qa.loc[~unavailable_combo1, "status"].eq("PASS").all()
    assert combo2_qa["status"].eq("PASS").all()
    assert len(stages) == 12
