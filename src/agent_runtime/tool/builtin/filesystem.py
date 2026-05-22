from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.tool.base import BaseTool, ToolException


class PathArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="文件或目录路径")


class ReadFileArgs(PathArgs):
    encoding: str = Field("utf-8", description="文件编码")


class WriteFileArgs(PathArgs):
    content: str = Field(..., description="写入内容")
    encoding: str = Field("utf-8", description="文件编码")
    append: bool = Field(False, description="是否追加写入")


class ListDirArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(".", description="目录路径")


class WorkspaceFileTool(BaseTool):
    """Base class for filesystem tools constrained to a workspace root."""

    def __init__(
            self,
            workspace_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()

    def _resolve_workspace_path(
            self,
            path: str,
    ) -> Path:
        raw_path = str(path).strip()
        if not raw_path:
            raise ToolException("路径不能为空", suggestion="请提供 args.path。")

        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate

        resolved = candidate.resolve(strict=False)

        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise ToolException(
                "路径超出 workspace",
                suggestion=f"请使用 {self.workspace_root} 下的路径。",
            )

        return resolved


class ReadFileTool(WorkspaceFileTool):
    name = "read_file"
    description = "读取本地文件内容，返回文本。"
    input_schema = ReadFileArgs
    preconditions = ["path 必须存在且是文件"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", "")))
        if not path.exists():
            raise ToolException("文件不存在", suggestion="请检查路径是否正确。")
        if not path.is_file():
            raise ToolException("路径不是文件", suggestion="请传入文件路径。")

        encoding = str(kwargs.get("encoding", "utf-8")).strip() or "utf-8"
        try:
            with path.open("r", encoding=encoding) as handle:
                content = handle.read()
        except OSError as exc:
            raise ToolException("读取文件失败", suggestion=str(exc)) from exc
        except UnicodeError as exc:
            raise ToolException("文件编码错误", suggestion="请确认 encoding 参数。") from exc

        return {"content": content, "data": {"path": str(path), "length": len(content)}}


class WriteFileTool(WorkspaceFileTool):
    name = "write_file"
    description = "写入本地文件内容。"
    input_schema = WriteFileArgs
    preconditions = ["path 必须非空"]
    side_effects = ["写入或追加本地文件"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", "")))

        content = str(kwargs.get("content", ""))
        encoding = str(kwargs.get("encoding", "utf-8")).strip() or "utf-8"
        append = bool(kwargs.get("append", False))
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with path.open("a" if append else "w", encoding=encoding) as handle:
                handle.write(content)
        except OSError as exc:
            raise ToolException("写入文件失败", suggestion=str(exc)) from exc

        return {
            "content": f"文件写入成功: {path}",
            "data": {"path": str(path), "length": len(content), "append": append},
        }


class DeleteFileTool(WorkspaceFileTool):
    name = "delete_file"
    description = "删除本地文件。"
    input_schema = PathArgs
    preconditions = ["path 必须存在且是文件"]
    side_effects = ["删除本地文件"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", "")))
        if not path.exists():
            raise ToolException("文件不存在")
        if not path.is_file():
            raise ToolException("路径不是文件")

        try:
            path.unlink()
        except OSError as exc:
            raise ToolException("删除文件失败", suggestion=str(exc)) from exc

        return {"content": f"文件删除成功: {path}", "data": {"path": str(path)}}


class FileExistsTool(WorkspaceFileTool):
    name = "file_exists"
    description = "检查文件或目录是否存在。"
    input_schema = PathArgs
    preconditions = ["path 必须非空"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", "")))
        exists = path.exists()
        return {
            "content": f"路径存在: {path}" if exists else f"路径不存在: {path}",
            "data": {"path": str(path), "exists": exists},
        }


class ListDirTool(WorkspaceFileTool):
    name = "list_dir"
    description = "列出目录中的文件和子目录。"
    input_schema = ListDirArgs
    preconditions = ["path 必须存在且是目录"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", ".")).strip() or ".")
        if not path.exists():
            raise ToolException("目录不存在", suggestion="请检查 args.path 是否正确。")
        if not path.is_dir():
            raise ToolException("路径不是目录", suggestion="请提供目录路径。")

        try:
            items = sorted(path.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise ToolException("读取目录失败", suggestion=str(exc)) from exc

        result = []
        for item in items:
            result.append({"name": item.name, "is_dir": item.is_dir()})

        return {
            "content": "\n".join(
                f"[DIR] {x['name']}" if x["is_dir"] else f"[FILE] {x['name']}"
                for x in result
            ),
            "data": {"path": str(path), "items": result, "count": len(result)},
        }


class MakeDirTool(WorkspaceFileTool):
    name = "make_dir"
    description = "创建目录。"
    input_schema = PathArgs
    preconditions = ["path 必须非空"]
    side_effects = ["创建本地目录"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = self._resolve_workspace_path(str(kwargs.get("path", "")))

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ToolException("创建目录失败", suggestion=str(exc)) from exc

        return {"content": f"目录创建成功: {path}", "data": {"path": str(path)}}
