from __future__ import annotations

import shlex

from agent_runtime.schema.policy import PolicyDecision
from agent_runtime.tool.resolver import ResolvedTool


class PolicyEngine:
    """执行前策略校验。"""

    def check(self, resolved: ResolvedTool) -> PolicyDecision:
        tool = resolved.tool

        if tool.name == "shell_exec":
            return self._check_shell_exec(resolved)

        return PolicyDecision(
            allowed=True,
            reason="tool policy allowed",
        )

    def _check_shell_exec(self, resolved: ResolvedTool) -> PolicyDecision:
        command = str(resolved.args.get("command", "")).strip()
        if not command:
            return PolicyDecision(
                allowed=False,
                reason="shell_exec command 不能为空",
            )

        specialized = self._specialized_tool_for_command(command)
        if specialized:
            return PolicyDecision(
                allowed=False,
                reason="shell_exec 不能替代已有专用工具",
                requires_approval=True,
                suggestion=f"请改用 {specialized}",
            )

        return PolicyDecision(
            allowed=False,
            reason="shell_exec 是高风险通用 Tool，默认需要外部审批",
            requires_approval=True,
        )

    @staticmethod
    def _specialized_tool_for_command(command: str) -> str | None:
        try:
            parts = shlex.split(command)
        except ValueError:
            return None

        if not parts:
            return None

        if parts[0] in {"cat", "sed", "head", "tail"}:
            return "read_file"
        if parts[0] in {"ls", "find"}:
            return "list_dir"
        if parts[0] == "mkdir":
            return "make_dir"
        if parts[0] == "rm":
            return "delete_file"
        if ">" in parts or ">>" in parts:
            return "write_file"

        return None
