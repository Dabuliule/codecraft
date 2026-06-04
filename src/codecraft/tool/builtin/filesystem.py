from __future__ import annotations

import difflib
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


class WriteFileArgs(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"
    create_parent_dirs: bool = False


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write text content to a file inside the workspace."
    args_schema = WriteFileArgs
    effects = {ToolEffect.WORKSPACE_WRITE}
    requires_approval = True

    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        write_args = WriteFileArgs.model_validate(args)
        guard = WorkspaceGuard(context.context.workspace_roots)
        path = guard.resolve_write_path(write_args.path, context.context.cwd)

        if path.exists() and path.is_dir():
            return ToolResult(
                success=False,
                content="Cannot write file because path is a directory.",
                error="path_is_directory",
                metadata={"path": str(path)},
            )

        if not path.parent.exists():
            if not write_args.create_parent_dirs:
                return ToolResult(
                    success=False,
                    content="Parent directory does not exist.",
                    error="parent_directory_missing",
                    suggestion="Set create_parent_dirs=true or create the parent directory first.",
                    metadata={"path": str(path), "parent": str(path.parent)},
                )
            path.parent.mkdir(parents=True, exist_ok=True)

        previous = path.read_text(encoding=write_args.encoding) if path.exists() else None
        path.write_text(write_args.content, encoding=write_args.encoding)

        status = "created" if previous is None else "modified"
        changed = previous != write_args.content
        diff = self._diff(
            before=previous or "",
            after=write_args.content,
            path=path,
        )
        return ToolResult(
            success=True,
            content=f"{status} {path}",
            data={
                "path": str(path),
                "status": status,
                "changed": changed,
                "diff": diff,
            },
            metadata={
                "path": str(path),
                "status": status,
                "changed": changed,
                "bytes": len(write_args.content.encode(write_args.encoding)),
            },
        )

    @staticmethod
    def _diff(*, before: str, after: str, path: Path) -> str:
        return "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
            )
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
