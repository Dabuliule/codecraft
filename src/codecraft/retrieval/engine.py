from __future__ import annotations

from collections.abc import Sequence

from codecraft.retrieval.models import RetrievalRequest, RetrievalResponse
from codecraft.retrieval.retrievers import Retriever, ScanRetriever


class ContextEngine:
    """Retrieval boundary used by tools and future query routing."""

    def __init__(
        self,
        retrievers: Sequence[Retriever] | None = None,
        *,
        default_retriever: str | None = None,
    ) -> None:
        configured = tuple(retrievers) if retrievers is not None else (ScanRetriever(),)
        if not configured:
            raise ValueError("context engine requires at least one retriever")
        names = [retriever.name for retriever in configured]
        if len(names) != len(set(names)):
            raise ValueError("context engine retrievers must have unique names")
        self._retrievers = {retriever.name: retriever for retriever in configured}
        self._default_retriever = default_retriever or names[0]
        if self._default_retriever not in self._retrievers:
            raise ValueError(f"unknown default retriever: {self._default_retriever}")

    @property
    def retriever_names(self) -> tuple[str, ...]:
        return tuple(self._retrievers)

    async def retrieve(
        self,
        request: RetrievalRequest,
        *,
        retriever_name: str | None = None,
    ) -> RetrievalResponse:
        selected = retriever_name or self._default_retriever
        try:
            retriever = self._retrievers[selected]
        except KeyError as exc:
            raise ValueError(f"unknown retriever: {selected}") from exc
        return await retriever.retrieve(request)
