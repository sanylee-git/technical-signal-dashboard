from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kospi_macro5_runtime.engine import (  # noqa: E402
    D1C1Context,
    replay_frozen_signals,
    run_live_adapter_probe,
    sha256_file,
    write_json,
)


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KOSPI_ROOT = Path("/Users/ibaeksan/Documents/프로젝트/macro_dashboard_kospi")
KOSPI_ROOT = Path(os.environ.get("KOSPI_MACRO_ROOT", DEFAULT_KOSPI_ROOT))


def main() -> None:
    ctx = D1C1Context(DASHBOARD_ROOT, KOSPI_ROOT)
    ctx.report_dir.mkdir(exist_ok=True)

    c1a = replay_frozen_signals(ctx)
    c1b = {
        "gate": "SKIPPED_KOSPI_MACRO5_D1C1B_REQUIRES_C1A_PASS",
        "reason": "C1-A did not pass",
    }
    if c1a["gate"] == "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY":
        c1b = run_live_adapter_probe(ctx)

    source_status_path = ctx.report_dir / "kospi_macro5_d1c1b_live_source_status.csv"
    if "source_status" in c1b:
        pd.DataFrame(c1b["source_status"]).to_csv(source_status_path, index=False)

    summary_rows = [
        {"gate_name": "C1-A Frozen Replay Parity", "gate": c1a["gate"]},
        {"gate_name": "C1-B Live Adapter Probe", "gate": c1b["gate"]},
    ]
    summary_path = ctx.report_dir / "kospi_macro5_d1c1_gate_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

    final_gate = (
        "PASS_KOSPI_MACRO5_D1C1_FROZEN_ENGINE_READY_LIVE_REVIEW"
        if c1a["gate"] == "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY"
        and str(c1b["gate"]).startswith("REVIEW_")
        else (
            "PASS_KOSPI_MACRO5_D1C1_LIVE_ENGINE_READY"
            if c1a["gate"] == "PASS_KOSPI_MACRO5_D1C1A_FROZEN_REPLAY_PARITY_READY"
            and c1b["gate"] == "PASS_KOSPI_MACRO5_D1C1B_LOCAL_LIVE_SMOKE_READY"
            else "BLOCKED_KOSPI_MACRO5_D1C1"
        )
    )

    manifest = {
        "gate": final_gate,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_stage": "D1-C1_KOSPI_MACRO5_LIVE_ENGINE_AND_FROZEN_PARITY",
        "official_operating_model": False,
        "dashboard_applied": False,
        "shadow_mode": True,
        "c1a": c1a,
        "c1b": c1b,
        "full_live_extension_ready": c1b["gate"] == "PASS_KOSPI_MACRO5_D1C1B_LOCAL_LIVE_SMOKE_READY",
        "live_freshness_policy_checked": False,
        "live_freshness_policy_stage": "D1-C2",
        "output_files": {
            "gate_summary": str(summary_path.relative_to(DASHBOARD_ROOT)),
            "live_source_status": str(source_status_path.relative_to(DASHBOARD_ROOT))
            if source_status_path.exists()
            else None,
            "report": "reports/kospi_macro5_d1c1_live_engine_report.md",
        },
    }
    manifest_path = ctx.report_dir / "kospi_macro5_d1c1_manifest.json"
    write_json(manifest_path, manifest)

    report = f"""# KOSPI Macro5 D1-C1 Live Engine & Frozen Parity

Final Gate: `{final_gate}`

## C1-A Frozen Replay

- Gate: `{c1a['gate']}`
- Core/component mismatch count: {c1a.get('core15_state_mismatch_count')}
- Final raw/T+1 mismatch count: {c1a.get('combo_final_t1_mismatch_count')}
- Reference final rows: {c1a.get('reference_final_rows')}
- Replay final rows: {c1a.get('replay_final_rows')}
- Reference component rows: {c1a.get('reference_component_rows')}
- Replay component rows: {c1a.get('replay_component_rows')}

## C1-B Live Adapter Probe

- Gate: `{c1b['gate']}`
- Live tail appended: {c1b.get('live_tail_appended', False)}
- Missing live bindings: {len(c1b.get('missing_live_bindings', []))}
- Live freshness policy: deferred to D1-C2

## Contract Notes

- Combo2 input is child Combo1 raw risk_state.
- Child Combo1 T+1 is not used inside Combo2.
- Final9 T+1 is applied once only.
- Missing signal values are not treated as Risk-on.
- Dashboard UI integration is not part of D1-C1.
"""
    report_path = ctx.report_dir / "kospi_macro5_d1c1_live_engine_report.md"
    report_path.write_text(report)
    manifest["output_files"]["manifest"] = str(manifest_path.relative_to(DASHBOARD_ROOT))
    manifest["output_files"]["report_sha256"] = sha256_file(report_path)
    write_json(manifest_path, manifest)

    print(json.dumps({"gate": final_gate, "c1a_gate": c1a["gate"], "c1b_gate": c1b["gate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
