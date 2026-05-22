from __future__ import annotations

from agent_runtime.policy.engine import PolicyEngine
from agent_runtime.schema.tool import ToolCall
from agent_runtime.tool.builtin.system import ShellExecTool
from agent_runtime.tool.resolver import ResolvedTool


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


def test_policy_rejects_empty_shell_command():
    decision = PolicyEngine().check(resolve_shell(""))

    assert decision.allowed is False
    assert decision.requires_approval is False
    assert decision.reason == "shell_exec command 不能为空"


def test_policy_rejects_shell_when_specialized_tool_exists():
    decision = PolicyEngine().check(resolve_shell("cat README.md"))

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.reason == "shell_exec 不能替代已有专用工具"
    assert decision.suggestion == "请改用 read_file"


def test_policy_rejects_generic_shell_by_default():
    decision = PolicyEngine().check(resolve_shell("python -V"))

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.reason == "shell_exec 是高风险通用 Tool，默认需要外部审批"
