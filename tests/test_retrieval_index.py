from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from codecraft.cli.app import app
from codecraft.retrieval import (
    ContextEngine,
    LexicalRetriever,
    RepositoryIndex,
    RetrievalRequest,
    ScanRetriever,
)
from codecraft.retrieval.chunking import TreeSitterChunker
from codecraft.retrieval.suite import seed_retrieval_workspace

runner = CliRunner()


def test_tree_sitter_chunker_extracts_multi_language_symbols(tmp_path):
    chunker = TreeSitterChunker(max_lines=20, overlap_lines=2)

    python = chunker.chunk(
        tmp_path / "agent.py",
        "class Agent:\n    def run(self):\n        return True\n",
    )
    typescript = chunker.chunk(
        tmp_path / "gateway.ts",
        "export class Gateway {\n  charge(): boolean { return true; }\n}\n",
    )
    go = chunker.chunk(
        tmp_path / "worker.go",
        "package worker\nfunc Run() bool { return true }\n",
    )

    assert python.language == "python"
    assert {(symbol.name, symbol.kind) for symbol in python.symbols} >= {
        ("Agent", "class_definition"),
        ("run", "function_definition"),
    }
    assert any(symbol.name == "Gateway" for symbol in typescript.symbols)
    assert any(symbol.name == "Run" for symbol in go.symbols)
    assert all(chunk.start_line <= chunk.end_line for chunk in python.chunks)


def test_repository_index_syncs_incrementally_and_queries_fts(tmp_path):
    workspace = tmp_path / "workspace"
    seed_retrieval_workspace(workspace)
    index = RepositoryIndex(tmp_path / "indexes")

    first = index.sync(workspace)
    second = index.sync(workspace)
    lexical = index.search_lexical(
        workspace,
        query="where are user permissions checked",
        max_results=5,
    )
    symbols = index.search_symbols(
        workspace,
        query="PaymentGateway",
        max_results=5,
    )

    assert first.candidate_file_count == 12
    assert first.indexed_file_count == 12
    assert first.updated_file_count == 12
    assert first.chunk_count >= 12
    assert first.symbol_count >= 8
    assert second.updated_file_count == 0
    assert second.unchanged_file_count == 12
    permissions_match = next(
        match for match in lexical.matches if match.path == "src/auth/permissions.py"
    )
    assert permissions_match.line == 2
    assert "ROLE_PERMISSIONS" in permissions_match.snippet
    assert symbols.matches[0].path == "src/services/payment_gateway.ts"

    service = workspace / "src/auth/service.py"
    service.write_text(
        service.read_text(encoding="utf-8")
        + "\ndef token_subject():\n    return None\n",
        encoding="utf-8",
    )
    updated = index.sync(workspace)
    assert updated.updated_file_count == 1
    assert updated.unchanged_file_count == 11

    (workspace / "docs/payments.md").unlink()
    deleted = index.sync(workspace)
    assert deleted.deleted_file_count == 1
    assert deleted.indexed_file_count == 11


def test_repository_index_skips_escaped_symlinks_and_its_database(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.py").write_text("def local(): pass\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("def secret(): pass\n", encoding="utf-8")
    (workspace / "escaped.py").symlink_to(outside)
    index = RepositoryIndex(workspace / ".codecraft" / "indexes")

    first = index.sync(workspace)
    second = index.sync(workspace)

    assert first.indexed_file_count == 1
    assert second.indexed_file_count == 1
    assert second.unchanged_file_count == 1


def test_context_engine_falls_back_when_index_match_is_stale(tmp_path):
    workspace = tmp_path / "workspace"
    seed_retrieval_workspace(workspace)
    index = RepositoryIndex(tmp_path / "indexes")
    index.sync(workspace)
    service = workspace / "src/auth/service.py"
    service.write_text(
        service.read_text(encoding="utf-8") + "\n# changed after indexing\n",
        encoding="utf-8",
    )
    engine = ContextEngine([ScanRetriever(), LexicalRetriever(index)])
    request = RetrievalRequest(
        query="validate_access_token",
        root=workspace,
        workspace_roots=(workspace,),
        mode="content",
    )

    response = asyncio.run(
        engine.retrieve(
            request,
            retriever_name="lexical",
            fallback_retriever="scan",
        )
    )

    assert response.retriever == "scan"
    assert response.fallback_from == "lexical"
    assert response.matches[0].path == "src/auth/service.py"


def test_index_command_reports_incremental_counts(tmp_path):
    workspace = tmp_path / "workspace"
    seed_retrieval_workspace(workspace)
    home = tmp_path / ".codecraft"

    first = runner.invoke(
        app,
        ["index", str(workspace), "--codecraft-home", str(home)],
    )
    second = runner.invoke(
        app,
        ["index", str(workspace), "--codecraft-home", str(home)],
    )

    assert first.exit_code == 0, first.output
    assert "indexed=12 updated=12 unchanged=0 deleted=0" in first.output
    assert second.exit_code == 0, second.output
    assert "indexed=12 updated=0 unchanged=12 deleted=0" in second.output
    assert list((home / "indexes").glob("*/index.sqlite3"))
