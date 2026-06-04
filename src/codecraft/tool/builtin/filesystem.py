from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from codecraft.core.errors import WorkspaceAccessError
from codecraft.schema.tool import ToolEffect, ToolResult
from codecraft.tool.base import BaseTool, ToolContext
from codecraft.tool.workspace import WorkspaceGuard


class ReadFileArgs(BaseModel):
    path: str
    encoding: str = "utf-8"
    max_chars: int = Field(default=80_000, ge=1)


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a text file inside the workspace."
    args_schema = ReadFileArgs
    effects = {ToolEffect.READ_ONLY}

    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        read_args = ReadFileArgs.model_validate(args)
        guard = WorkspaceGuard(context.context.workspace_roots)
        path = guard.resolve_read_path(read_args.path, context.context.cwd)

        if path.is_dir():
            return ToolResult(
                success=False,
                content="Cannot read a directory.",
                error="path_is_directory",
                metadata={"path": str(path)},
            )

        try:
            content = path.read_text(encoding=read_args.encoding)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                content="File does not exist.",
                error="file_not_found",
                metadata={"path": str(path)},
            )
        except UnicodeDecodeError as exc:
            return ToolResult(
                success=False,
                content="File could not be decoded.",
                error=str(exc),
                suggestion="Try a different encoding.",
                metadata={"path": str(path), "encoding": read_args.encoding},
            )

        truncated = len(content) > read_args.max_chars
        visible = content[: read_args.max_chars]
        return ToolResult(
            success=True,
            content=visible,
            data={
                "path": str(path),
                "line_count": len(content.splitlines()),
                "truncated": truncated,
            },
            metadata={
                "path": str(path),
                "chars": len(content),
                "returned_chars": len(visible),
                "truncated": truncated,
            },
        )


class ListFilesArgs(BaseModel):
    path: str = "."
    recursive: bool = False
    max_entries: int = Field(default=500, ge=1)


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories inside the workspace."
    args_schema = ListFilesArgs
    effects = {ToolEffect.READ_ONLY}

    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        list_args = ListFilesArgs.model_validate(args)
        guard = WorkspaceGuard(context.context.workspace_roots)
        path = guard.resolve_read_path(list_args.path, context.context.cwd)

        if not path.exists():
            return ToolResult(
                success=False,
                content="Path does not exist.",
                error="path_not_found",
                metadata={"path": str(path)},
            )

        if path.is_file():
            entries = [path]
        else:
            entries = self._iter_entries(path, recursive=list_args.recursive)

        visible_entries = []
        skipped_names = {".git", "__pycache__", ".venv", "node_modules"}
        for entry in entries:
            if any(part in skipped_names for part in entry.relative_to(path).parts):
                continue
            visible_entries.append(entry)
            if len(visible_entries) >= list_args.max_entries:
                break

        lines = [self._format_entry(entry, path) for entry in visible_entries]
        return ToolResult(
            success=True,
            content="\n".join(lines),
            data={
                "path": str(path),
                "entries": lines,
                "truncated": len(visible_entries) >= list_args.max_entries,
            },
            metadata={
                "path": str(path),
                "count": len(lines),
                "recursive": list_args.recursive,
            },
        )

    @staticmethod
    def _iter_entries(path: Path, *, recursive: bool) -> list[Path]:
        if recursive:
            return sorted(path.rglob("*"))
        return sorted(path.iterdir())

    @staticmethod
    def _format_entry(entry: Path, root: Path) -> str:
        suffix = "/" if entry.is_dir() else ""
        try:
            relative = entry.relative_to(root)
        except ValueError as exc:
            raise WorkspaceAccessError(
                "listed path escaped root",
                code="workspace_access_denied",
            ) from exc
        return f"{relative}{suffix}"
