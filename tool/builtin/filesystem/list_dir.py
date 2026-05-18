"""内置目录列表工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class ListDirArgs(BaseModel):
    """目录列表输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ".",
        description="目录路径",
    )


class ListDirTool(BaseTool):
    """列出目录内容。"""

    name = "list_dir"

    description = "列出目录中的文件和子目录。"

    args_schema = ListDirArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:

        path = str(kwargs.get("path", ".")).strip() or "."

        if not os.path.exists(path):
            raise ToolException(
                "目录不存在",
                suggestion="请检查 path 是否正确。",
            )

        if not os.path.isdir(path):
            raise ToolException(
                "路径不是目录",
                suggestion="请提供目录路径。",
            )

        try:
            items = sorted(os.listdir(path))

        except OSError as exc:
            raise ToolException(
                "读取目录失败",
                suggestion=str(exc),
            ) from exc

        result = []

        for item in items:
            full_path = os.path.join(path, item)

            result.append({
                "name": item,
                "is_dir": os.path.isdir(full_path),
            })

        return {
            "content": "\n".join(
                [
                    f"[DIR] {x['name']}"
                    if x["is_dir"]
                    else f"[FILE] {x['name']}"
                    for x in result
                ]
            ),
            "data": {
                "path": path,
                "items": result,
                "count": len(result),
            },
        }

