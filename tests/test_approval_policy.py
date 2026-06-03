from __future__ import annotations

from codecraft.policy.approval import DefaultApprovalPolicy
from codecraft.schema.tool import ToolCall


def test_write_file_new_workspace_file_does_not_require_approval(tmp_path):
    policy = DefaultApprovalPolicy(workspace_root=tmp_path)

    request = policy.build_request(
        approval_id="approval-1",
        tool_call=ToolCall(
            tool="write_file",
            args={"path": "new.txt", "content": "hello"},
        ),
    )

    assert request is None


def test_write_file_existing_workspace_file_requires_approval(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    policy = DefaultApprovalPolicy(workspace_root=tmp_path)

    request = policy.build_request(
        approval_id="approval-1",
        tool_call=ToolCall(
            tool="write_file",
            args={"path": "existing.txt", "content": "new"},
        ),
    )

    assert request is not None
    assert request.tool_call.tool == "write_file"
    assert request.data["risk_level"] == "medium"


def test_write_file_outside_workspace_requires_approval(tmp_path):
    policy = DefaultApprovalPolicy(workspace_root=tmp_path)

    request = policy.build_request(
        approval_id="approval-1",
        tool_call=ToolCall(
            tool="write_file",
            args={"path": "../outside.txt", "content": "new"},
        ),
    )

    assert request is not None


def test_delete_file_requires_approval(tmp_path):
    policy = DefaultApprovalPolicy(workspace_root=tmp_path)

    request = policy.build_request(
        approval_id="approval-1",
        tool_call=ToolCall(
            tool="delete_file",
            args={"path": "target.txt"},
        ),
    )

    assert request is not None
    assert request.tool_call.tool == "delete_file"


def test_make_dir_does_not_require_approval(tmp_path):
    policy = DefaultApprovalPolicy(workspace_root=tmp_path)

    request = policy.build_request(
        approval_id="approval-1",
        tool_call=ToolCall(
            tool="make_dir",
            args={"path": "new-dir"},
        ),
    )

    assert request is None
