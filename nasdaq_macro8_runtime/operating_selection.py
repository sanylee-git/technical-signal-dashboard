"""Integrity-checked display selection for the NASDAQ operating Final10."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "nasdaq_macro8_assets/nasdaq_macro8_operating_final10.json"
MANIFEST_PATH = ROOT / "nasdaq_macro8_assets/nasdaq_macro8_operating_final10_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_operating_selection() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("gate") != "PASS_NASDAQ_OPERATING_FINAL10_SELECTION":
        raise RuntimeError("NASDAQ operating Final10 manifest is not PASS")
    asset = manifest.get("asset", {})
    if asset.get("path") != ASSET_PATH.relative_to(ROOT).as_posix():
        raise RuntimeError("NASDAQ operating Final10 asset path mismatch")
    if _sha256(ASSET_PATH) != asset.get("sha256") or ASSET_PATH.stat().st_size != asset.get("bytes"):
        raise RuntimeError("NASDAQ operating Final10 asset integrity check failed")
    data = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    if data.get("contract") != "nasdaq_operating_final10_display_v1":
        raise RuntimeError("NASDAQ operating Final10 selection contract failed")
    candidates = data.get("candidates", [])
    frame = pd.DataFrame(candidates)
    counts = frame.groupby("family")["candidate_id"].nunique().to_dict()
    if len(frame) != 10 or frame["candidate_id"].duplicated().any() or counts != {"Combo1": 5, "Combo2": 5}:
        raise RuntimeError("NASDAQ operating Final10 must contain five unique candidates per combo")
    if not frame["designation"].isin(["MAIN", "Confirm"]).all():
        raise RuntimeError("NASDAQ operating Final10 designation is invalid")
    for family, group in frame.groupby("family"):
        if sorted(group["display_order"].astype(int).tolist()) != [1, 2, 3, 4, 5]:
            raise RuntimeError(f"NASDAQ operating Final10 order is invalid for {family}")
        main = group.loc[group["designation"].eq("MAIN")]
        if len(main) != 1 or int(main.iloc[0]["display_order"]) != 1:
            raise RuntimeError(f"NASDAQ operating Final10 must have one first-position MAIN for {family}")
    return candidates
