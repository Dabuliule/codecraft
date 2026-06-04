from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from codecraft.sandbox.command_policy import CommandPolicy, CommandRisk
from codecraft.schema.tool import ToolEffect, ToolResult
from codecraft.tool.base import BaseTool, ToolContext
from codecraft.tool.workspace import WorkspaceGuard


class BashArgs(BaseModel):
    command: str
    cwd: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class BashTool(BaseTool):
    name = "bash"
    description = "Run a shell command from inside the workspace."
    args_schema = BashArgs
    effects = {ToolEffect.PROCESS_EXEC}
    requires_approval = True

    def __init__(self, command_policy: CommandPolicy | None = None) -> None:
        self.command_policy = command_policy or CommandPolicy()

    async def arun(self, args: BaseModel, context: ToolContext) -> ToolResult:
        bash_args = BashArgs.model_validate(args)
        guard = WorkspaceGuard(context.context.workspace_roots)
        cwd = self._resolve_cwd(bash_args.cwd, context, guard)
        decision = self.command_policy.classify(
            bash_args.command,
            network_access=context.context.network_access,
        )

        if decision.risk == CommandRisk.DENY:
            return ToolResult(
                success=False,
                content="Command denied by policy.",
                error="command_denied",
                suggestion=decision.reason,
                metadata={"command": bash_args.command, "risk": decision.risk},
            )

        if decision.requires_approval and not context.approved:
            return ToolResult(
                success=False,
                content="Command requires approval.",
                error="command_requires_approval",
                suggestion=decision.reason,
                metadata={"command": bash_args.command, "risk": decision.risk},
            )

        try:
            process = await asyncio.create_subprocess_shell(
                bash_args.command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=bash_args.timeout_seconds,
            )
            timed_out = False
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            timed_out = True

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        stdout, stdout_truncated = self._truncate(stdout, context.context.max_tool_output_chars)
        stderr, stderr_truncated = self._truncate(stderr, context.context.max_tool_output_chars)
        exit_code = process.returncode
        success = exit_code == 0 and not timed_out

        return ToolResult(
            success=success,
            content=stdout if success else stderr or stdout or "Command failed.",
            data={
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": timed_out,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
            error=None if success else ("command_timed_out" if timed_out else "command_failed"),
            metadata={
                "command": bash_args.command,
                "cwd": str(cwd),
                "risk": decision.risk,
            },
        )

    @staticmethod
    def _resolve_cwd(
        cwd: str | None,
        context: ToolContext,
        guard: WorkspaceGuard,
    ) -> Path:
        if cwd is None:
            return context.context.cwd
        resolved = guard.resolve_read_path(cwd, context.context.cwd)
        if not resolved.is_dir():
            raise NotADirectoryError(str(resolved))
        return resolved

    @staticmethod
    def _truncate(value: str, max_chars: int) -> tuple[str, bool]:
        if len(value) <= max_chars:
            return value, False
        return value[:max_chars], True
