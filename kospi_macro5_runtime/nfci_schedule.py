from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay


NFCI_RELEASE_CONTRACT_VERSION = "nfci_weekly_friday_plus_3_bday_v1"


def nfci_schedule_for_observation(observation_date: object) -> dict[str, object]:
    obs = pd.Timestamp(observation_date).normalize()
    release = (obs + BDay(3)).normalize()
    return {
        "observation_week_ending_date": obs.strftime("%Y-%m-%d"),
        "expected_release_date": release.strftime("%Y-%m-%d"),
        "expected_available_date": release.strftime("%Y-%m-%d"),
        "expected_krx_aligned_date": release.strftime("%Y-%m-%d"),
        "next_expected_release_date": (release + BDay(5)).normalize().strftime("%Y-%m-%d"),
        "release_contract_version": NFCI_RELEASE_CONTRACT_VERSION,
        "official_schedule_bound": True,
        "heuristic_14day_used": False,
    }


def nfci_freshness_status(latest_observation_date: object, as_of_utc: object) -> tuple[str, dict[str, object]]:
    if latest_observation_date is None or pd.isna(latest_observation_date):
        return "FETCH_ERROR", {"official_schedule_bound": True, "heuristic_14day_used": False}
    schedule = nfci_schedule_for_observation(latest_observation_date)
    as_of_date = pd.Timestamp(as_of_utc)
    if as_of_date.tzinfo is not None:
        as_of_date = as_of_date.tz_convert("UTC").tz_localize(None)
    as_of_date = as_of_date.normalize()
    release = pd.Timestamp(schedule["expected_release_date"])
    next_release = pd.Timestamp(schedule["next_expected_release_date"])
    if as_of_date < next_release:
        return "NO_NEW_RELEASE_EXPECTED", schedule
    if as_of_date <= next_release + BDay(1):
        return "EXPECTED_CADENCE_LAG", schedule
    return "STALE", schedule
