from __future__ import annotations

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
    protected_tools = {
        "delete_file",
        "make_dir",
        "shell_exec",
        "write_file",
    }

    def build_request(
            self,
            *,
            approval_id: str,
            tool_call: ToolCall,
    ) -> ApprovalRequest | None:
        if tool_call.tool in self.read_only_tools:
            return None

        if tool_call.tool not in self.protected_tools:
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
