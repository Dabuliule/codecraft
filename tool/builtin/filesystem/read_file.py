"""内置文件读取工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class ReadFileArgs(BaseModel):
    """读取文件的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="要读取的文件路径")
    encoding: str = Field("utf-8", description="文件编码")


class ReadFileTool(BaseTool):
    """读取本地文件内容。"""

    name = "read_file"
    description = "读取本地文件内容，返回文本。"
    args_schema = ReadFileArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()
        if not path:
            raise ToolException("文件路径不能为空", suggestion="请提供 path 参数。")
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

        return {
            "content": content,
            "data": {"path": path, "length": len(content)},
        }

