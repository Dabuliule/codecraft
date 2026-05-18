"""内置 Bash 执行工具。"""

from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tool.base import BaseTool, ToolException


class BashArgs(BaseModel):
    """执行 Bash 命令的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="要执行的 Bash 命令")
    cwd: str | None = Field(None, description="命令执行目录")
    timeout: int = Field(30, description="超时时间（秒）")


class BashTool(BaseTool):
    """执行本地 Bash 命令。"""

    name = "bash"
    description = "执行本地 Bash 命令，返回 stdout/stderr。"
    args_schema = BashArgs

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        command = str(kwargs.get("command", "")).strip()
        if not command:
            raise ToolException(
                "命令不能为空",
                suggestion="请提供 command 参数。",
            )

        cwd = kwargs.get("cwd")
        timeout = int(kwargs.get("timeout", 30))

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolException(
                "命令执行超时",
                suggestion=f"请增加 timeout，当前超时时间为 {timeout} 秒。",
            ) from exc
        except OSError as exc:
            raise ToolException(
                "命令执行失败",
                suggestion=str(exc),
            ) from exc

        return {
            "content": result.stdout.strip(),
            "data": {
                "command": command,
                "cwd": cwd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        }
