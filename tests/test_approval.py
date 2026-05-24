from __future__ import annotations

import pytest

from codecraft.core.approval import ApprovalFlow
from codecraft.schema.policy import PolicyDecision
from codecraft.schema.tool import ToolCall
from codecraft.tool.builtin.system import ShellExecTool
from codecraft.tool.resolver import ResolvedTool


def resolve_shell() -> ResolvedTool:
    tool = ShellExecTool()
    request = ToolCall(
        tool="shell_exec",
        args={"command": "python -V"},
    )
    return ResolvedTool(
        tool_call=request,
        tool=tool,
        args=tool.build_args(request),
    )


@pytest.mark.anyio
async def test_approval_flow_requires_bool_handler_result():
    approval_flow = ApprovalFlow(
        handler=lambda event: "yes",
    )

    with pytest.raises(TypeError, match="Approval handler must return bool"):
        await approval_flow.request(
            approval_id="approval-1",
            resolved=resolve_shell(),
            policy_decision=PolicyDecision.require_approval(
                reason="needs approval",
            ),
        )
