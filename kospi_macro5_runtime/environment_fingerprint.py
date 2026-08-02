from __future__ import annotations

import hashlib
import importlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _version(name: str) -> str:
    try:
        mod = importlib.import_module(name)
        return str(getattr(mod, "__version__", "UNKNOWN"))
    except Exception:
        return "NOT_INSTALLED"


def hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        if not path.exists() or not path.is_file():
            continue
        h.update(str(path.name).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def environment_fingerprint(runtime_root: Path, *, contract_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    files = list(Path(runtime_root).glob("*.py"))
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "timezone": datetime.now().astimezone().tzname(),
        "pandas_version": _version("pandas"),
        "numpy_version": _version("numpy"),
        "pyarrow_version": _version("pyarrow"),
        "yfinance_version": _version("yfinance"),
        "curl_cffi_version": _version("curl_cffi"),
        "requests_version": _version("requests"),
        "calendar_package": "portable_internal_krx_calendar",
        "calendar_package_version": "d1c2a_krx_calendar_v1_20260802",
        "runtime_code_hash": hash_files(files),
        "contract_hashes": contract_hashes or {},
    }


def fingerprint_json(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
