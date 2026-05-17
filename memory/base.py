from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from schema.memory import MemoryItem


class MemoryStore(ABC):
    """Minimal memory store interface."""

    @abstractmethod
    def add(self, item: MemoryItem) -> MemoryItem:
        """Add a memory item and return it."""
        raise NotImplementedError

    def add_many(self, items: Iterable[MemoryItem]) -> List[MemoryItem]:
        """Add multiple memory items."""
        added: List[MemoryItem] = []
        for item in items:
            added.append(self.add(item))
        return added

    @abstractmethod
    def list(self) -> List[MemoryItem]:
        """Return all memory items."""
        raise NotImplementedError

    @abstractmethod
    def recent(self, limit: int = 10, *, role: Optional[str] = None) -> List[MemoryItem]:
        """Return most recent items, optionally filtered by role."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, *, limit: int = 10, role: Optional[str] = None) -> List[MemoryItem]:
        """Return items matching the query string."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Clear all items."""
        raise NotImplementedError

