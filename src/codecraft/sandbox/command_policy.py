from __future__ import annotations

import shlex
from enum import StrEnum

from pydantic import BaseModel


class CommandRisk(StrEnum):
    SAFE = "safe"
    PROMPT = "prompt"
    DENY = "deny"


class CommandDecision(BaseModel):
    risk: CommandRisk
    reason: str
    requires_approval: bool


class CommandPolicy:
    SAFE_COMMANDS = {
        "pwd",
        "ls",
        "rg",
        "grep",
        "cat",
        "sed",
        "git",
        "pytest",
        "python",
        "uv",
        "npm",
        "mvn",
    }
    PROMPT_COMMANDS = {
        "pip",
        "poetry",
        "curl",
        "wget",
        "ssh",
        "scp",
        "rm",
        "mv",
        "chmod",
        "chown",
        "git-clean",
        "git-commit",
        "git-push",
    }
    DENY_COMMANDS = {
        "sudo",
        "dd",
        "mkfs",
    }
    NETWORK_COMMANDS = {
        "curl",
        "wget",
        "ssh",
        "scp",
    }

    def classify(self, command: str, *, network_access: bool = False) -> CommandDecision:
        parts = self._split(command)
        if not parts:
            return CommandDecision(
                risk=CommandRisk.DENY,
                reason="empty command",
                requires_approval=False,
            )

        executable = parts[0]
        compound = self._compound_name(parts)

        if executable in self.DENY_COMMANDS or "rm -rf /" in command:
            return CommandDecision(
                risk=CommandRisk.DENY,
                reason=f"{executable} is denied",
                requires_approval=False,
            )

        if executable in self.NETWORK_COMMANDS and not network_access:
            return CommandDecision(
                risk=CommandRisk.DENY,
                reason=f"{executable} requires network access",
                requires_approval=False,
            )

        if compound in self.PROMPT_COMMANDS or executable in self.PROMPT_COMMANDS:
            return CommandDecision(
                risk=CommandRisk.PROMPT,
                reason=f"{compound} requires approval",
                requires_approval=True,
            )

        if self._is_known_safe(parts):
            return CommandDecision(
                risk=CommandRisk.SAFE,
                reason="command is classified as safe",
                requires_approval=False,
            )

        return CommandDecision(
            risk=CommandRisk.PROMPT,
            reason="unknown command requires approval",
            requires_approval=True,
        )

    @staticmethod
    def _split(command: str) -> list[str]:
        try:
            return shlex.split(command)
        except ValueError:
            return []

    @staticmethod
    def _compound_name(parts: list[str]) -> str:
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}"
        return parts[0]

    def _is_known_safe(self, parts: list[str]) -> bool:
        executable = parts[0]
        if executable not in self.SAFE_COMMANDS:
            return False

        if executable == "git" and len(parts) >= 2:
            return parts[1] in {"status", "diff", "show", "log"}

        if executable == "uv" and len(parts) >= 3:
            return parts[1:3] in (["run", "pytest"], ["run", "ruff"])

        if executable == "npm" and len(parts) >= 2:
            return parts[1] in {"test", "run"}

        if executable == "python" and len(parts) >= 3:
            return parts[1:3] == ["-m", "pytest"]

        return executable in {"pwd", "ls", "rg", "grep", "cat", "sed", "pytest", "mvn"}
