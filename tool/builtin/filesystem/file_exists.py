"""文件存在检查工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool


class FileExistsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description="文件路径",
    )


class FileExistsTool(BaseTool):
    name = "file_exists"

    description = "检查文件或目录是否存在。"

    args_schema = FileExistsArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", "")).strip()

        exists = os.path.exists(path)

        return {
            "content": (
                f"路径存在: {path}"
                if exists
                else f"路径不存在: {path}"
            ),
            "data": {
                "path": path,
                "exists": exists,
            },
        }

