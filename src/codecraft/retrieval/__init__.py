from typing import Any

from codecraft.retrieval.engine import ContextEngine
from codecraft.retrieval.errors import RetrievalUnavailableError
from codecraft.retrieval.index import IndexSyncStats, RepositoryIndex
from codecraft.retrieval.models import (
    RetrievalMatch,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStats,
)
from codecraft.retrieval.report import render_retrieval_html, render_retrieval_json
from codecraft.retrieval.retrievers import (
    LexicalRetriever,
    Retriever,
    ScanRetriever,
    SymbolRetriever,
)
from codecraft.retrieval.suite import (
    RETRIEVAL_SUITE_NAME,
    RetrievalCase,
    get_retrieval_cases,
    seed_retrieval_workspace,
)

__all__ = [
    "RETRIEVAL_SUITE_NAME",
    "ContextEngine",
    "IndexSyncStats",
    "LexicalRetriever",
    "RepositoryIndex",
    "Retriever",
    "RetrievalCase",
    "RetrievalMatch",
    "RetrievalMode",
    "RetrievalRequest",
    "RetrievalResponse",
    "RetrievalStats",
    "RetrievalUnavailableError",
    "ScanRetriever",
    "SymbolRetriever",
    "get_retrieval_cases",
    "render_retrieval_html",
    "render_retrieval_json",
    "run_retrieval_benchmark",
    "seed_retrieval_workspace",
]


def __getattr__(name: str) -> Any:
    if name == "run_retrieval_benchmark":
        from codecraft.retrieval.benchmark import run_retrieval_benchmark

        return run_retrieval_benchmark
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
