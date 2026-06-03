from __future__ import annotations

import pytest

from codecraft.schema.approval import ApprovalDecision
from codecraft.schema.tool import ToolCall


def test_approval_decision_accepts_approve_reject_and_edit():
    edited = ToolCall(
        tool="shell_exec",
        args={"command": "python -V"},
    )

    assert ApprovalDecision.approve().action == "approve"
    assert ApprovalDecision.reject().action == "reject"
    assert ApprovalDecision.edit(edited).edited_tool_call == edited


def test_edit_approval_requires_edited_tool_call():
    with pytest.raises(ValueError, match="edit approval requires edited_tool_call"):
        ApprovalDecision(action="edit")


def test_non_edit_approval_rejects_edited_tool_call():
    edited = ToolCall(
        tool="shell_exec",
        args={"command": "python -V"},
    )

    with pytest.raises(ValueError, match="edited_tool_call is only valid"):
        ApprovalDecision(
            action="approve",
            edited_tool_call=edited,
        )
