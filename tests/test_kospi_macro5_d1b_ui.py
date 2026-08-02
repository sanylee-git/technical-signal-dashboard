import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "kospi_macro5_assets"
SOURCE = ROOT / "technical_signal_dashboard.py"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _macro4_block_hash() -> str:
    lines = SOURCE.read_text(errors="ignore").splitlines()
    start = next(i for i, line in enumerate(lines) if "def render_macro4_combo_section" in line)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("def render_macro5_kospi_section") or stripped.startswith("def render_macro5_final8_section") or lines[i].startswith("    elif page =="):
            end = i
            break
    return hashlib.sha256("\n".join(lines[start:end]).encode()).hexdigest()


def test_d1a_asset_integrity_and_final9_coverage():
    manifest = json.loads((ASSET_DIR / "kospi_final9_dashboard_manifest.json").read_text())
    ui_manifest = json.loads((ASSET_DIR / "kospi_macro5_d1b_ui_manifest.json").read_text())
    assert manifest["gate"] == "PASS_WITH_RECOMPUTED_COMBO1_REFERENCE_SIGNALS"
    assert ui_manifest["gate"] == "PASS_KOSPI_MACRO5_D1B_UI_ASSET_COVERAGE"
    assert manifest["candidate_count"] == 9
    assert manifest["combo1_count"] == 4
    assert manifest["combo2_count"] == 5
    assert manifest["official_operating_model"] is False
    assert manifest["dashboard_applied"] is False

    checksums = json.loads((ASSET_DIR / "checksums.json").read_text())
    for name, meta in checksums.items():
        path = ASSET_DIR / name
        assert path.exists()
        assert _sha256(path) == meta["sha256"]

    metrics = pd.read_csv(ASSET_DIR / "kospi_final9_candidate_metrics.csv")
    signals = pd.read_parquet(ASSET_DIR / "kospi_final9_reference_signals.parquet")
    assert metrics["candidate_id"].nunique() == 9
    assert signals["candidate_id"].nunique() == 9
    assert signals.duplicated(["candidate_id", "date"]).sum() == 0
    assert {"candidate_id", "date", "raw_risk_state", "t1_position"}.issubset(signals.columns)


def test_macro5_kospi_route_and_isolation_tokens():
    text = SOURCE.read_text(errors="ignore")
    assert '"macro5_kospi": ("KOSPI MACRO INDICATORS", "🇰🇷 매크로 지표 5")' in text
    assert '("macro5_kospi", "🇰🇷 매크로 지표 5")' in text
    assert 'def render_macro5_kospi_section' in text
    assert 'key="macro5_kospi_preset"' in text
    assert 'key="macro5_kospi_years"' in text
    assert 'key="macro5_kospi_show_raw"' in text
    macro5_section = text.split("def render_macro5_kospi_section", 1)[1].split("def render_macro5_final8_section", 1)[0]
    assert "_yf_close(" not in macro5_section
    assert "yf.download" not in macro5_section
    assert "FRED" not in macro5_section
    assert "macro4_preset" not in macro5_section
    assert "Final9 다수결" in macro5_section


def test_macro4_reference_preserved_and_no_runtime_absolute_path():
    manifest = json.loads((ASSET_DIR / "kospi_final9_dashboard_manifest.json").read_text())
    assert _macro4_block_hash() == manifest["macro4_reference_hash"]["sha256"]
    text = SOURCE.read_text(errors="ignore")
    assert "/Users/ibaeksan" not in text
    ui_manifest = json.loads((ASSET_DIR / "kospi_macro5_d1b_ui_manifest.json").read_text())
    assert "/Users/ibaeksan" not in json.dumps(ui_manifest, ensure_ascii=False)


def test_d1b_support_asset_schema():
    benchmark = pd.read_parquet(ASSET_DIR / "kospi_final9_benchmark_close.parquet")
    components = pd.read_parquet(ASSET_DIR / "kospi_final9_component_reference_signals.parquet")
    snapshot = pd.read_parquet(ASSET_DIR / "kospi_final9_ui_snapshot_reference.parquet")
    assert {"date", "kospi_close"}.issubset(benchmark.columns)
    assert {"parent_candidate_id", "component_id", "date", "component_risk_state", "valid_signal"}.issubset(components.columns)
    assert snapshot["candidate_id"].nunique() == 9
    assert components["parent_candidate_id"].nunique() == 9
    benchmark_dates = pd.to_datetime(benchmark["date"])
    assert benchmark_dates.min() <= pd.Timestamp("1996-12-11")
    assert benchmark_dates.max() >= pd.Timestamp("2026-07-28")
