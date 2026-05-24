from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from codecraft.tool.base import BaseTool, ToolException


class ShellExecArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="要执行的 shell 命令")
    cwd: str | None = Field(None, description="命令执行目录")
    timeout: int = Field(30, description="超时时间（秒）")


class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = "执行本地 shell 命令。仅作为高风险通用逃生入口。"
    input_schema = ShellExecArgs
    preconditions = ["command 必须非空", "没有更专用 Tool 能满足该工具调用"]
    side_effects = ["可能读取或修改本地环境，取决于 command"]
    tags = {"system", "generic"}
    risk_level = "high"
    generic = True
    max_output_chars = 8000
    denied_commands = {
        "chmod",
        "chown",
        "dd",
        "kill",
        "pkill",
        "reboot",
        "rm",
        "shutdown",
        "su",
        "sudo",
    }

    def __init__(
            self,
            workspace_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        command = str(kwargs.get("command", "")).strip()
        if not command:
            raise ToolException("命令不能为空", suggestion="请提供 args.command。")

        argv = self._parse_command(command)
        self._reject_dangerous_command(argv)

        cwd = self._resolve_cwd(kwargs.get("cwd"))
        timeout = int(kwargs.get("timeout", 30))

        try:
            result = subprocess.run(
                argv,
                shell=False,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._safe_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolException(
                "命令执行超时",
                suggestion=f"请增加 timeout，当前超时时间为 {timeout} 秒。",
            ) from exc
        except OSError as exc:
            raise ToolException("命令执行失败", suggestion=str(exc)) from exc

        return {
            "success": result.returncode == 0,
            "content": self._content(result),
            "data": {
                "command": command,
                "argv": argv,
                "cwd": str(cwd),
                "returncode": result.returncode,
                "stdout": self._truncate(result.stdout),
                "stderr": self._truncate(result.stderr),
            },
            "error": (
                f"命令退出码非零: {result.returncode}"
                if result.returncode != 0
                else None
            ),
        }

    @staticmethod
    def _parse_command(
            command: str,
    ) -> list[str]:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ToolException("命令解析失败", suggestion=str(exc)) from exc

        if not argv:
            raise ToolException("命令不能为空", suggestion="请提供 args.command。")

        return argv

    def _reject_dangerous_command(
            self,
            argv: list[str],
    ) -> None:
        executable = Path(argv[0]).name
        if executable in self.denied_commands:
            raise ToolException(
                "危险命令被拒绝",
                suggestion="请改用受控专用工具或更安全的命令。",
            )

    def _resolve_cwd(
            self,
            cwd: Any,
    ) -> Path:
        raw_cwd = str(cwd).strip() if cwd is not None else "."
        if not raw_cwd:
            raw_cwd = "."

        candidate = Path(raw_cwd)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate

        resolved = candidate.resolve(strict=False)

        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise ToolException(
                "cwd 超出 workspace",
                suggestion=f"请使用 {self.workspace_root} 下的 cwd。",
            )

        return resolved

    @staticmethod
    def _safe_env() -> dict[str, str]:
        allowed = {
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "PYTHONPATH",
            "VIRTUAL_ENV",
        }
        return {
            key: value
            for key, value in os.environ.items()
            if key in allowed
        }

    def _content(
            self,
            result: subprocess.CompletedProcess[str],
    ) -> str:
        if result.stdout.strip():
            return self._truncate(result.stdout.strip())

        return self._truncate(result.stderr.strip())

    def _truncate(
            self,
            text: str,
    ) -> str:
        if len(text) <= self.max_output_chars:
            return text

        omitted = len(text) - self.max_output_chars
        return f"{text[:self.max_output_chars].rstrip()}\n... truncated {omitted} chars"
