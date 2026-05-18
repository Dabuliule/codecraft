"""内置文件写入工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class WriteFileArgs(BaseModel):
    """写入文件输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="文件路径")

    content: str = Field(
        ...,
        description="写入内容",
    )

    encoding: str = Field(
        "utf-8",
        description="文件编码",
    )

    append: bool = Field(
        False,
        description="是否追加写入",
    )


class WriteFileTool(BaseTool):
    """写入本地文件。"""

    name = "write_file"

    description = "写入本地文件内容。"

    args_schema = WriteFileArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:

        path = str(kwargs.get("path", "")).strip()

        if not path:
            raise ToolException(
                "文件路径不能为空",
                suggestion="请提供 path 参数。",
            )

        content = str(kwargs.get("content", ""))

        encoding = str(
            kwargs.get("encoding", "utf-8")
        ).strip() or "utf-8"

        append = bool(kwargs.get("append", False))

        parent = os.path.dirname(path)

        if parent:
            os.makedirs(parent, exist_ok=True)

        mode = "a" if append else "w"

        try:
            with open(
                    path,
                    mode,
                    encoding=encoding,
            ) as handle:
                handle.write(content)

        except OSError as exc:
            raise ToolException(
                "写入文件失败",
                suggestion=str(exc),
            ) from exc

        return {
            "content": f"文件写入成功: {path}",
            "data": {
                "path": path,
                "length": len(content),
                "append": append,
            },
        }

