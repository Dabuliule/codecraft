"""内置目录创建工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.tool.base import BaseTool, ToolException


class MakeDirArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description="目录路径",
    )


class MakeDirTool(BaseTool):
    name = "make_dir"

    description = "创建目录。"

    args_schema = MakeDirArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:

        path = str(kwargs.get("path", "")).strip()

        if not path:
            raise ToolException(
                "目录路径不能为空",
            )

        try:
            os.makedirs(path, exist_ok=True)

        except OSError as exc:
            raise ToolException(
                "创建目录失败",
                suggestion=str(exc),
            ) from exc

        return {
            "content": f"目录创建成功: {path}",
            "data": {
                "path": path,
            },
        }

