from __future__ import annotations

import shlex

from agent_runtime.operation.resolver import ResolvedOperation
from agent_runtime.schema.policy import PolicyDecision


class PolicyEngine:
    """执行前策略校验。"""

    def check(self, resolved: ResolvedOperation) -> PolicyDecision:
        operation = resolved.operation

        if operation.intent == "shell.exec":
            return self._check_shell_exec(resolved)

        return PolicyDecision(
            allowed=True,
            reason="operation policy allowed",
        )

    def _check_shell_exec(self, resolved: ResolvedOperation) -> PolicyDecision:
        command = str(resolved.args.get("command", "")).strip()
        if not command:
            return PolicyDecision(
                allowed=False,
                reason="shell.exec command 不能为空",
            )

        specialized = self._specialized_intent_for_command(command)
        if specialized:
            return PolicyDecision(
                allowed=False,
                reason="shell.exec 不能替代已有专用 intent",
                requires_approval=True,
                suggestion=f"请改用 {specialized}",
            )

        return PolicyDecision(
            allowed=False,
            reason="shell.exec 是高风险通用 Operation，默认需要外部审批",
            requires_approval=True,
        )

    @staticmethod
    def _specialized_intent_for_command(command: str) -> str | None:
        try:
            parts = shlex.split(command)
        except ValueError:
            return None

        if not parts:
            return None

        if parts[0] in {"cat", "sed", "head", "tail"}:
            return "filesystem.read"
        if parts[0] in {"ls", "find"}:
            return "filesystem.list"
        if parts[0] == "mkdir":
            return "filesystem.make_dir"
        if parts[0] == "rm":
            return "filesystem.delete"
        if ">" in parts or ">>" in parts:
            return "filesystem.write"

        return None
