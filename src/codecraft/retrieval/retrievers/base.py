from __future__ import annotations

from abc import ABC, abstractmethod

from codecraft.retrieval.models import RetrievalRequest, RetrievalResponse


class Retriever(ABC):
    name: str

    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse: ...
