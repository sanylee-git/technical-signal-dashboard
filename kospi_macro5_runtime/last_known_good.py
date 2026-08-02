from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LastKnownGoodStore:
    def load_source_state(self, source_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def save_source_state(self, source_id: str, state: dict[str, Any]) -> None:
        raise NotImplementedError

    def load_candidate_snapshot(self, candidate_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def save_candidate_snapshot(self, candidate_id: str, snapshot: dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryLastKnownGoodStore(LastKnownGoodStore):
    def __init__(self) -> None:
        self.sources: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Any]] = {}

    def load_source_state(self, source_id: str) -> dict[str, Any] | None:
        return self.sources.get(source_id)

    def save_source_state(self, source_id: str, state: dict[str, Any]) -> None:
        self.sources[source_id] = dict(state)

    def load_candidate_snapshot(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidates.get(candidate_id)

    def save_candidate_snapshot(self, candidate_id: str, snapshot: dict[str, Any]) -> None:
        self.candidates[candidate_id] = dict(snapshot)


class LocalFileLastKnownGoodStore(LastKnownGoodStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        (self.root / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "candidates").mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self.root / kind / f"{safe}.json"

    def _load(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _save(self, path: Path, value: dict[str, Any]) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")

    def load_source_state(self, source_id: str) -> dict[str, Any] | None:
        return self._load(self._path("sources", source_id))

    def save_source_state(self, source_id: str, state: dict[str, Any]) -> None:
        self._save(self._path("sources", source_id), state)

    def load_candidate_snapshot(self, candidate_id: str) -> dict[str, Any] | None:
        return self._load(self._path("candidates", candidate_id))

    def save_candidate_snapshot(self, candidate_id: str, snapshot: dict[str, Any]) -> None:
        self._save(self._path("candidates", candidate_id), snapshot)


def date_regressed(current: str | None, previous: str | None) -> bool:
    if not current or not previous:
        return False
    return str(current) < str(previous)
