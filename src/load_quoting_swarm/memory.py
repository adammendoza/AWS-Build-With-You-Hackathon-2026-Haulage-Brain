from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class MemoryItem:
    value: str
    metadata: dict[str, Any]


class _CrewAIStorage:
    """Minimal storage backend used to exercise CrewAI Memory without an embedder."""

    def __init__(self) -> None:
        self.items: list[tuple[Any, dict[str, Any]]] = []

    def save(self, value: Any, metadata: dict[str, Any]) -> None:
        self.items.append((value, dict(metadata)))

    def search(
        self, query: str, limit: int, score_threshold: float
    ) -> list[dict[str, Any]]:
        del score_threshold
        needle = query.casefold()
        return [
            {"value": value, "metadata": metadata}
            for value, metadata in self.items
            if needle in str(value).casefold()
        ][:limit]

    def reset(self) -> None:
        self.items.clear()


class ScopedMemory:
    """Small scope-enforcing adapter; optionally mirrors writes into CrewAI Memory."""

    ALLOWED_SCOPES = frozenset({"/pricing", "/compliance", "/fleet-fit", "/supervisor"})

    def __init__(self, *, use_crewai: bool = False):
        self._items: dict[str, list[MemoryItem]] = defaultdict(list)
        self._lock = Lock()
        self._crewai = None
        if use_crewai:
            try:
                # CrewAI 1.9 exports concrete memories from ``crewai.memory`` but
                # keeps the reusable Memory class in this module.
                from crewai.memory.memory import Memory

                self._crewai = Memory(storage=_CrewAIStorage())
            except (ImportError, TypeError) as exc:
                raise RuntimeError("CrewAI Memory could not be initialized") from exc

    def _validate_scope(self, scope: str) -> None:
        if scope not in self.ALLOWED_SCOPES:
            raise ValueError(f"memory scope is not allowed: {scope}")

    def remember(self, value: str, *, scope: str, metadata: dict[str, Any]) -> None:
        self._validate_scope(scope)
        item = MemoryItem(value=value, metadata=dict(metadata))
        with self._lock:
            self._items[scope].append(item)
        if self._crewai is not None:
            self._crewai.save(value, metadata={**metadata, "scope": scope})

    def recall(self, *, scope: str, metadata_key: str, metadata_value: str) -> list[MemoryItem]:
        self._validate_scope(scope)
        with self._lock:
            return [
                item
                for item in self._items[scope]
                if str(item.metadata.get(metadata_key, "")).casefold()
                == metadata_value.casefold()
            ]
