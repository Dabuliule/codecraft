from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from codecraft.retrieval.errors import RetrievalUnavailableError
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
        fallback_retriever: str | None = None,
    ) -> RetrievalResponse:
        selected = retriever_name or self._default_retriever
        try:
            retriever = self._retrievers[selected]
        except KeyError as exc:
            if fallback_retriever is None:
                raise ValueError(f"unknown retriever: {selected}") from exc
            return await self._fallback(request, selected, fallback_retriever)
        try:
            response = await retriever.retrieve(request)
        except RetrievalUnavailableError:
            if fallback_retriever is None or fallback_retriever == selected:
                raise
            return await self._fallback(request, selected, fallback_retriever)
        return replace(response, retriever=selected)

    async def _fallback(
        self,
        request: RetrievalRequest,
        selected: str,
        fallback: str,
    ) -> RetrievalResponse:
        try:
            retriever = self._retrievers[fallback]
        except KeyError as exc:
            raise ValueError(f"unknown fallback retriever: {fallback}") from exc
        response = await retriever.retrieve(request)
        return replace(response, retriever=fallback, fallback_from=selected)
