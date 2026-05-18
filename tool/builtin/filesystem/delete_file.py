"""内置文件删除工具。"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class DeleteFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description="文件路径",
    )


class DeleteFileTool(BaseTool):
    name = "delete_file"

    description = "删除本地文件。"

    args_schema = DeleteFileArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:

        path = str(kwargs.get("path", "")).strip()

        if not os.path.exists(path):
            raise ToolException(
                "文件不存在",
            )

        if not os.path.isfile(path):
            raise ToolException(
                "路径不是文件",
            )

        try:
            os.remove(path)

        except OSError as exc:
            raise ToolException(
                "删除文件失败",
                suggestion=str(exc),
            ) from exc

        return {
            "content": f"文件删除成功: {path}",
            "data": {
                "path": path,
            },
        }

