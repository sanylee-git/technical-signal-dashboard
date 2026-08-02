"""KOSPI Macro5 runtime helpers.

This package is intentionally independent from the Streamlit UI.  It is used
to replay the frozen KOSPI Macro5 Final9 signals and to probe whether live
adapters can be wired without changing Macro4/Macro5 page code.
"""

from .engine import (
    D1C1Context,
    build_dependency_graph,
    replay_frozen_signals,
    run_live_adapter_probe,
)

__all__ = [
    "D1C1Context",
    "build_dependency_graph",
    "replay_frozen_signals",
    "run_live_adapter_probe",
]
