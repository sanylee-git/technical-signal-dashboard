from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nasdaq_macro8_runtime.frozen_runtime import run_frozen_runtime


def test_final20_frozen_runtime_has_one_verified_cutoff() -> None:
    payload = run_frozen_runtime()
    snapshot = payload["snapshot"]
    assert payload["runtime_mode"] == "FROZEN_ONLY"
    assert payload["network_access"] is False
    assert payload["proxy_only"] is True
    assert payload["direct_oas_used"] is False
    assert len(snapshot) == 20
    assert snapshot["calculable"].all()
    assert snapshot["basis_date"].nunique() == 1
    assert snapshot["basis_date"].iloc[0] == "2026-08-21"
    assert snapshot["active_count"].ge(0).all()
    assert snapshot["active_count"].le(snapshot["K"] * 4).all()
