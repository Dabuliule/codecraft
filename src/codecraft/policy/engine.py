from __future__ import annotations

import shlex

from codecraft.schema.policy import PolicyDecision
from codecraft.tool.resolver import ResolvedTool


class PolicyEngine:
    """执行前策略校验。"""

    def check(self, resolved: ResolvedTool) -> PolicyDecision:
        tool = resolved.tool

        if tool.name == "shell_exec":
            return self._check_shell_exec(resolved)

        return PolicyDecision.allow(
            reason="tool policy allowed",
            data=self._tool_context(resolved),
        )

    def _check_shell_exec(self, resolved: ResolvedTool) -> PolicyDecision:
        command = str(resolved.args.get("command", "")).strip()
        if not command:
            return PolicyDecision.deny(
                reason="shell_exec command 不能为空",
                data=self._tool_context(resolved),
            )

        specialized = self._specialized_tool_for_command(command)
        if specialized:
            return PolicyDecision.deny(
                reason="shell_exec 不能替代已有专用工具",
                suggestion=f"请改用 {specialized}",
                data={
                    **self._tool_context(resolved),
                    "specialized_tool": specialized,
                },
            )

        return PolicyDecision.require_approval(
            reason="shell_exec 是高风险通用 Tool，默认需要外部审批",
            data=self._tool_context(resolved),
        )

    @staticmethod
    def _tool_context(resolved: ResolvedTool) -> dict[str, object]:
        tool = resolved.tool
        return {
            "tool": tool.name,
            "risk_level": str(getattr(tool.risk_level, "value", tool.risk_level)),
            "tags": sorted(tool.tags),
            "generic": tool.generic,
        }

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
