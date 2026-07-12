from __future__ import annotations

import asyncio

import pytest

from codecraft.retrieval import (
    ContextEngine,
    RetrievalMatch,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStats,
    Retriever,
    ScanRetriever,
)


class StaticRetriever(Retriever):
    name = "static"

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        return RetrievalResponse(
            matches=(
                RetrievalMatch(
                    type="content",
                    path="virtual/result.py",
                    line=7,
                    snippet=request.query,
                ),
            ),
            stats=RetrievalStats(candidate_file_count=1, scanned_file_count=1),
        )


def test_scan_retriever_preserves_path_content_and_costs(tmp_path):
    source = tmp_path / "src" / "agent.py"
    source.parent.mkdir()
    source.write_text("def build_agent():\n    return 'ready'\n", encoding="utf-8")
    ignored = tmp_path / "__pycache__" / "agent.py"
    ignored.parent.mkdir()
    ignored.write_text("def build_agent(): pass\n", encoding="utf-8")
    request = RetrievalRequest(
        query="agent",
        root=tmp_path,
        workspace_roots=(tmp_path,),
    )

    response = asyncio.run(ScanRetriever().retrieve(request))

    assert [match.as_dict() for match in response.matches] == [
        {"type": "path", "path": "src/agent.py"},
        {
            "type": "content",
            "path": "src/agent.py",
            "line": 1,
            "snippet": "def build_agent():",
        },
    ]
    assert response.stats.candidate_file_count == 1
    assert response.stats.scanned_file_count == 1
    assert response.stats.read_file_count == 1
    assert response.stats.scanned_bytes == source.stat().st_size


def test_context_engine_selects_configured_retrievers(tmp_path):
    request = RetrievalRequest(
        query="needle",
        root=tmp_path,
        workspace_roots=(tmp_path,),
    )
    engine = ContextEngine(
        [ScanRetriever(), StaticRetriever()],
        default_retriever="static",
    )

    default_response = asyncio.run(engine.retrieve(request))
    scan_response = asyncio.run(engine.retrieve(request, retriever_name="scan"))

    assert engine.retriever_names == ("scan", "static")
    assert default_response.matches[0].path == "virtual/result.py"
    assert scan_response.matches == ()
    with pytest.raises(ValueError, match="unknown retriever: missing"):
        asyncio.run(engine.retrieve(request, retriever_name="missing"))


def test_context_engine_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="unique names"):
        ContextEngine([ScanRetriever(), ScanRetriever()])
    with pytest.raises(ValueError, match="unknown default retriever"):
        ContextEngine([ScanRetriever()], default_retriever="missing")
