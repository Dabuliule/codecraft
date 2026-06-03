from __future__ import annotations

from pathlib import Path

from codecraft.schema.approval import ApprovalRequest
from codecraft.schema.tool import ToolCall


class ApprovalPolicy:
    """Decide whether a tool action needs human approval."""

    def build_request(
            self,
            *,
            approval_id: str,
            tool_call: ToolCall,
    ) -> ApprovalRequest | None:
        raise NotImplementedError


class DefaultApprovalPolicy(ApprovalPolicy):
    read_only_tools = {
        "file_exists",
        "list_dir",
        "read_file",
    }

    def __init__(
            self,
            workspace_root: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()

    def build_request(
            self,
            *,
            approval_id: str,
            tool_call: ToolCall,
    ) -> ApprovalRequest | None:
        if tool_call.tool in self.read_only_tools:
            return None

        if tool_call.tool == "make_dir":
            return None

        if tool_call.tool == "write_file" and self._is_new_workspace_file(
                tool_call
        ):
            return None

        if tool_call.tool not in {
            "delete_file",
            "shell_exec",
            "write_file",
        }:
            return None

        risk_level = "high" if tool_call.tool == "shell_exec" else "medium"
        reason = f"{tool_call.tool} 需要人工审批"

        return ApprovalRequest(
            approval_id=approval_id,
            tool_call=tool_call,
            reason=reason,
            data={
                "tool": tool_call.tool,
                "risk_level": risk_level,
            },
        )

    def _is_new_workspace_file(
            self,
            tool_call: ToolCall,
    ) -> bool:
        path = self._resolve_workspace_path(tool_call.args.get("path"))
        if path is None:
            return False

        return not path.exists()

    def _resolve_workspace_path(
            self,
            value,
    ) -> Path | None:
        raw_path = str(value or "").strip()
        if not raw_path:
            return None

        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate

        resolved = candidate.resolve(strict=False)
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            return None

        return resolved
