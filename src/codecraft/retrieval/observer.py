from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from codecraft.core.turn_context import TurnContext
from codecraft.retrieval.errors import RetrievalUnavailableError
from codecraft.retrieval.index import RepositoryIndex
from codecraft.schema.tool import ToolCall, ToolResult


class WorkspaceIndexObserver:
    name = "workspace_index"

    def __init__(self, index: RepositoryIndex) -> None:
        self.index = index

    async def after_result(
        self,
        call: ToolCall,
        result: ToolResult,
        context: TurnContext,
    ) -> dict[str, Any] | None:
        paths = _changed_paths(call, result)
        if not paths:
            return None

        grouped = _group_by_workspace(paths, context.workspace_roots)
        if not grouped:
            return None

        async def refresh(root: Path, changed: list[Path]) -> dict[str, Any]:
            try:
                stats = await asyncio.to_thread(
                    self.index.refresh_paths,
                    root,
                    changed,
                )
            except RetrievalUnavailableError:
                return {
                    "workspace": str(root),
                    "status": "skipped",
                    "reason": "index_not_built",
                }
            return {
                "workspace": str(root),
                "status": "updated",
                "updated_files": stats.updated_file_count,
                "unchanged_files": stats.unchanged_file_count,
                "deleted_files": stats.deleted_file_count,
                "indexed_bytes": stats.indexed_bytes,
            }

        updates = await asyncio.gather(
            *(refresh(root, changed) for root, changed in grouped.items())
        )
        return {"workspaces": updates}


def _changed_paths(call: ToolCall, result: ToolResult) -> list[Path]:
    if not result.success or result.data is None:
        return []
    if call.name == "write_file":
        if result.data.get("changed") is not True:
            return []
        path = result.data.get("path")
        return [Path(path)] if isinstance(path, str) else []
    if call.name == "apply_patch":
        paths = result.data.get("changed_files")
        if not isinstance(paths, list):
            return []
        return [Path(path) for path in paths if isinstance(path, str)]
    return []


def _group_by_workspace(
    paths: list[Path], workspace_roots: list[Path]
) -> dict[Path, list[Path]]:
    roots = sorted(
        (root.expanduser().resolve() for root in workspace_roots),
        key=lambda root: len(root.parts),
        reverse=True,
    )
    grouped: dict[Path, list[Path]] = {}
    for path in paths:
        resolved = path.expanduser().resolve(strict=False)
        for root in roots:
            if resolved == root or root in resolved.parents:
                grouped.setdefault(root, []).append(resolved)
                break
    return grouped
