from __future__ import annotations

import pytest

from codecraft.core.approval import ApprovalBroker
from codecraft.schema.approval import ApprovalDecision
from codecraft.schema.event import ApprovalRequestEvent
from codecraft.schema.tool import ToolCall


def approval_event() -> ApprovalRequestEvent:
    return ApprovalRequestEvent(
        approval_id="approval-1",
        tool="shell_exec",
        args={"command": "python -V"},
        reason="needs approval",
    )


@pytest.mark.anyio
async def test_approval_broker_requires_structured_decision():
    broker = ApprovalBroker(
        handler=lambda event: "yes",
    )

    with pytest.raises(TypeError, match="Approval handler must return ApprovalDecision"):
        await broker.decide(approval_event())


@pytest.mark.anyio
async def test_approval_broker_accepts_approve_reject_and_edit():
    edited = ToolCall(
        tool="shell_exec",
        args={"command": "python -V"},
    )

    for decision in (
            ApprovalDecision.approve(),
            ApprovalDecision.reject(),
            ApprovalDecision.edit(edited),
    ):
        broker = ApprovalBroker(handler=lambda event, decision=decision: decision)

        result = await broker.decide(approval_event())

        assert result == decision


def test_edit_approval_requires_edited_tool_call():
    with pytest.raises(ValueError, match="edit approval requires edited_tool_call"):
        ApprovalDecision(decision="edit")
