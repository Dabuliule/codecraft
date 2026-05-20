from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.operation.base import BaseOperation, OperationException


class ShellExecArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="要执行的 shell 命令")
    cwd: str | None = Field(None, description="命令执行目录")
    timeout: int = Field(30, description="超时时间（秒）")


class ShellExecOperation(BaseOperation):
    name = "shell_exec"
    intent = "shell.exec"
    description = "执行本地 shell 命令。仅作为高风险通用逃生入口。"
    input_schema = ShellExecArgs
    preconditions = ["command 必须非空", "没有更专用 Operation 能满足该 intent"]
    side_effects = ["可能读取或修改本地环境，取决于 command"]
    tags = {"system", "generic"}
    risk_level = "high"
    generic = True

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        command = str(kwargs.get("command", "")).strip()
        if not command:
            raise OperationException("命令不能为空", suggestion="请提供 params.command。")

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
            raise OperationException(
                "命令执行超时",
                suggestion=f"请增加 timeout，当前超时时间为 {timeout} 秒。",
            ) from exc
        except OSError as exc:
            raise OperationException("命令执行失败", suggestion=str(exc)) from exc

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
