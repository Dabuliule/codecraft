from __future__ import annotations

import difflib
from pathlib import Path
from typing import Literal

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

        previous = (
            path.read_text(encoding=write_args.encoding) if path.exists() else None
        )
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


class WorkspaceSearchArgs(BaseModel):
    query: str = Field(min_length=1)
    path: str = "."
    mode: Literal["both", "content", "path"] = "both"
    case_sensitive: bool = False
    max_results: int = Field(default=100, ge=1, le=1000)
    max_file_bytes: int = Field(default=1_000_000, ge=1)


class WorkspaceSearchTool(BaseTool):
    name = "workspace_search"
    description = (
        "Search workspace file paths and text content, returning matching paths, "
        "line numbers, and snippets."
    )
    args_schema = WorkspaceSearchArgs
    effects = {ToolEffect.READ_ONLY}

    skipped_names = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }

    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        search_args = WorkspaceSearchArgs.model_validate(args)
        guard = WorkspaceGuard(context.context.workspace_roots)
        root = guard.resolve_read_path(search_args.path, context.context.cwd)

        if not root.exists():
            return ToolResult(
                success=False,
                content="Search path does not exist.",
                error="path_not_found",
                metadata={"path": str(root)},
            )

        files = [root] if root.is_file() else self._iter_files(root)
        query = (
            search_args.query
            if search_args.case_sensitive
            else search_args.query.casefold()
        )
        matches: list[dict[str, object]] = []
        skipped: dict[str, int] = {"binary": 0, "large": 0, "escaped": 0}
        scanned_file_count = 0
        read_file_count = 0
        scanned_bytes = 0

        for file_path in files:
            if len(matches) >= search_args.max_results:
                break

            if not self._is_safe_file(file_path, guard):
                skipped["escaped"] += 1
                continue

            scanned_file_count += 1
            display_path = self._display_path(file_path, guard.workspace_roots)
            if search_args.mode in {"both", "path"}:
                candidate_path = (
                    display_path
                    if search_args.case_sensitive
                    else display_path.casefold()
                )
                if query in candidate_path:
                    matches.append(
                        {
                            "type": "path",
                            "path": display_path,
                        }
                    )
                    if len(matches) >= search_args.max_results:
                        break

            if search_args.mode not in {"both", "content"}:
                continue

            stat = file_path.stat()
            if stat.st_size > search_args.max_file_bytes:
                skipped["large"] += 1
                continue

            try:
                raw = file_path.read_bytes()
            except OSError:
                continue

            read_file_count += 1
            scanned_bytes += len(raw)
            if self._looks_binary(raw):
                skipped["binary"] += 1
                continue

            text = raw.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                candidate_line = line if search_args.case_sensitive else line.casefold()
                if query not in candidate_line:
                    continue

                matches.append(
                    {
                        "type": "content",
                        "path": display_path,
                        "line": line_number,
                        "snippet": self._trim_line(line),
                    }
                )
                if len(matches) >= search_args.max_results:
                    break

        lines = [self._format_match(match) for match in matches]
        truncated = len(matches) >= search_args.max_results
        content = "\n".join(lines) if lines else "No matches found."

        return ToolResult(
            success=True,
            content=content,
            data={
                "query": search_args.query,
                "path": str(root),
                "matches": matches,
                "match_count": len(matches),
                "truncated": truncated,
                "skipped": skipped,
                "candidate_file_count": len(files),
                "scanned_file_count": scanned_file_count,
                "read_file_count": read_file_count,
                "scanned_bytes": scanned_bytes,
                "returned_chars": len(content),
            },
            metadata={
                "query": search_args.query,
                "path": str(root),
                "match_count": len(matches),
                "truncated": truncated,
                "candidate_file_count": len(files),
                "scanned_file_count": scanned_file_count,
                "read_file_count": read_file_count,
                "scanned_bytes": scanned_bytes,
                "returned_chars": len(content),
            },
        )

    @classmethod
    def _iter_files(cls, root: Path) -> list[Path]:
        return sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and not cls._has_skipped_part(path.relative_to(root))
        )

    @classmethod
    def _has_skipped_part(cls, relative: Path) -> bool:
        return any(part in cls.skipped_names for part in relative.parts)

    @staticmethod
    def _is_safe_file(path: Path, guard: WorkspaceGuard) -> bool:
        try:
            guard.assert_inside_workspace(path.resolve(strict=False))
        except WorkspaceAccessError:
            return False
        return True

    @staticmethod
    def _looks_binary(raw: bytes) -> bool:
        return b"\0" in raw[:4096]

    @staticmethod
    def _trim_line(line: str, max_chars: int = 240) -> str:
        normalized = line.strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1]}..."

    @staticmethod
    def _display_path(path: Path, workspace_roots: list[Path]) -> str:
        resolved = path.resolve(strict=False)
        for root in sorted(
            workspace_roots, key=lambda item: len(item.parts), reverse=True
        ):
            try:
                return str(resolved.relative_to(root))
            except ValueError:
                continue
        return str(path)

    @staticmethod
    def _format_match(match: dict[str, object]) -> str:
        if match["type"] == "path":
            return f"{match['path']} [path]"
        return f"{match['path']}:{match['line']}: {match['snippet']}"
