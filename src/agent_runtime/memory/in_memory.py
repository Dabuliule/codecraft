from __future__ import annotations

from typing import List, Optional

from agent_runtime.observability.trace import TraceLogger
from agent_runtime.schema.memory import MemoryItem

from .base import MemoryStore


class InMemoryStore(MemoryStore):
    """Simple in-memory memory store."""

    def __init__(self) -> None:
        self._items: List[MemoryItem] = []

    def add(self, item: MemoryItem) -> MemoryItem:
        self._items.append(item)
        TraceLogger.log(
            "memory.add",
            {"role": item.role, "content_len": len(item.content)},
            level="DEBUG",
        )
        return item

    def list(self) -> List[MemoryItem]:
        return list(self._items)

    def recent(self, limit: int = 10, *, role: Optional[str] = None) -> List[MemoryItem]:
        if limit <= 0:
            return []
        items = self._items
        if role:
            items = [item for item in items if item.role == role]
        return list(reversed(items))[:limit]

    def search(self, query: str, *, limit: int = 10, role: Optional[str] = None) -> List[MemoryItem]:
        if limit <= 0:
            return []
        query_lower = query.lower()
        items = self._items
        if role:
            items = [item for item in items if item.role == role]
        matched = [item for item in items if query_lower in item.content.lower()]
        return matched[:limit]

    def clear(self) -> None:
        self._items.clear()
