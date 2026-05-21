from __future__ import annotations

import os
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


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取本地文件内容，返回文本。"
    input_schema = ReadFileArgs
    preconditions = ["path 必须存在且是文件"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        if not path:
            raise ToolException("文件路径不能为空", suggestion="请提供 args.path。")
        if not os.path.exists(path):
            raise ToolException("文件不存在", suggestion="请检查路径是否正确。")
        if not os.path.isfile(path):
            raise ToolException("路径不是文件", suggestion="请传入文件路径。")

        encoding = str(kwargs.get("encoding", "utf-8")).strip() or "utf-8"
        try:
            with open(path, "r", encoding=encoding) as handle:
                content = handle.read()
        except OSError as exc:
            raise ToolException("读取文件失败", suggestion=str(exc)) from exc
        except UnicodeError as exc:
            raise ToolException("文件编码错误", suggestion="请确认 encoding 参数。") from exc

        return {"content": content, "data": {"path": path, "length": len(content)}}


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "写入本地文件内容。"
    input_schema = WriteFileArgs
    preconditions = ["path 必须非空"]
    side_effects = ["写入或追加本地文件"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        if not path:
            raise ToolException("文件路径不能为空", suggestion="请提供 args.path。")

        content = str(kwargs.get("content", ""))
        encoding = str(kwargs.get("encoding", "utf-8")).strip() or "utf-8"
        append = bool(kwargs.get("append", False))
        parent = os.path.dirname(path)

        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            with open(path, "a" if append else "w", encoding=encoding) as handle:
                handle.write(content)
        except OSError as exc:
            raise ToolException("写入文件失败", suggestion=str(exc)) from exc

        return {
            "content": f"文件写入成功: {path}",
            "data": {"path": path, "length": len(content), "append": append},
        }


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "删除本地文件。"
    input_schema = PathArgs
    preconditions = ["path 必须存在且是文件"]
    side_effects = ["删除本地文件"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        if not os.path.exists(path):
            raise ToolException("文件不存在")
        if not os.path.isfile(path):
            raise ToolException("路径不是文件")

        try:
            os.remove(path)
        except OSError as exc:
            raise ToolException("删除文件失败", suggestion=str(exc)) from exc

        return {"content": f"文件删除成功: {path}", "data": {"path": path}}


class FileExistsTool(BaseTool):
    name = "file_exists"
    description = "检查文件或目录是否存在。"
    input_schema = PathArgs
    preconditions = ["path 必须非空"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        exists = os.path.exists(path)
        return {
            "content": f"路径存在: {path}" if exists else f"路径不存在: {path}",
            "data": {"path": path, "exists": exists},
        }


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "列出目录中的文件和子目录。"
    input_schema = ListDirArgs
    preconditions = ["path 必须存在且是目录"]
    side_effects: list[str] = []
    tags = {"filesystem"}
    risk_level = "low"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", ".")).strip() or "."
        if not os.path.exists(path):
            raise ToolException("目录不存在", suggestion="请检查 args.path 是否正确。")
        if not os.path.isdir(path):
            raise ToolException("路径不是目录", suggestion="请提供目录路径。")

        try:
            items = sorted(os.listdir(path))
        except OSError as exc:
            raise ToolException("读取目录失败", suggestion=str(exc)) from exc

        result = []
        for item in items:
            full_path = os.path.join(path, item)
            result.append({"name": item, "is_dir": os.path.isdir(full_path)})

        return {
            "content": "\n".join(
                f"[DIR] {x['name']}" if x["is_dir"] else f"[FILE] {x['name']}"
                for x in result
            ),
            "data": {"path": path, "items": result, "count": len(result)},
        }


class MakeDirTool(BaseTool):
    name = "make_dir"
    description = "创建目录。"
    input_schema = PathArgs
    preconditions = ["path 必须非空"]
    side_effects = ["创建本地目录"]
    tags = {"filesystem"}
    risk_level = "medium"

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        if not path:
            raise ToolException("目录路径不能为空")

        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            raise ToolException("创建目录失败", suggestion=str(exc)) from exc

        return {"content": f"目录创建成功: {path}", "data": {"path": path}}
