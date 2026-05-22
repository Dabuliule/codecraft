from __future__ import annotations

from agent_runtime.policy.engine import PolicyEngine
from agent_runtime.schema.tool import ToolCall
from agent_runtime.tool.builtin.filesystem import ReadFileTool
from agent_runtime.tool.builtin.system import ShellExecTool
from agent_runtime.tool.resolver import ResolvedTool


def resolve_read_file() -> ResolvedTool:
    tool = ReadFileTool()
    request = ToolCall(
        tool="read_file",
        args={"path": "README.md"},
    )
    return ResolvedTool(
        tool_call=request,
        tool=tool,
        args=tool.build_args(request),
    )


def resolve_shell(command: str) -> ResolvedTool:
    tool = ShellExecTool()
    request = ToolCall(
        tool="shell_exec",
        args={"command": command},
    )
    return ResolvedTool(
        tool_call=request,
        tool=tool,
        args=tool.build_args(request),
    )


def test_policy_allows_non_shell_tools_with_context():
    decision = PolicyEngine().check(resolve_read_file())

    assert decision.action == "allow"
    assert decision.reason == "tool policy allowed"
    assert decision.data == {
        "tool": "read_file",
        "risk_level": "low",
        "tags": ["filesystem", "read"],
        "generic": False,
    }


def test_policy_rejects_empty_shell_command():
    decision = PolicyEngine().check(resolve_shell(""))

    assert decision.action == "deny"
    assert decision.reason == "shell_exec command 不能为空"
    assert decision.data["tool"] == "shell_exec"


def test_policy_rejects_shell_when_specialized_tool_exists():
    decision = PolicyEngine().check(resolve_shell("cat README.md"))

    assert decision.action == "deny"
    assert decision.reason == "shell_exec 不能替代已有专用工具"
    assert decision.suggestion == "请改用 read_file"
    assert decision.data["specialized_tool"] == "read_file"


def test_policy_rejects_generic_shell_by_default():
    decision = PolicyEngine().check(resolve_shell("python -V"))

    assert decision.action == "require_approval"
    assert decision.reason == "shell_exec 是高风险通用 Tool，默认需要外部审批"
    assert decision.data == {
        "tool": "shell_exec",
        "risk_level": "high",
        "tags": ["generic", "system"],
        "generic": True,
    }
