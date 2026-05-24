from __future__ import annotations

import pytest

from codecraft.tool.builtin.system import ShellExecTool
from codecraft.tool.factory import create_tool_registry


@pytest.mark.anyio
async def test_shell_exec_runs_without_shell_and_uses_workspace_cwd(tmp_path):
    result = await ShellExecTool(workspace_root=tmp_path).arun(
        {
            "command": "python -c 'import os; print(os.getcwd())'",
        }
    )

    assert result.success is True
    assert result.content == str(tmp_path)
    assert result.data["cwd"] == str(tmp_path)
    assert result.data["argv"] == [
        "python",
        "-c",
        "import os; print(os.getcwd())",
    ]


@pytest.mark.anyio
async def test_shell_exec_rejects_cwd_outside_workspace(tmp_path):
    result = await ShellExecTool(workspace_root=tmp_path).arun(
        {
            "command": "python -V",
            "cwd": str(tmp_path.parent),
        }
    )

    assert result.success is False
    assert result.error == "cwd 超出 workspace"
    assert result.suggestion == f"请使用 {tmp_path.resolve()} 下的 cwd。"


@pytest.mark.anyio
async def test_shell_exec_marks_nonzero_returncode_as_failure(tmp_path):
    result = await ShellExecTool(workspace_root=tmp_path).arun(
        {
            "command": "python -c 'import sys; sys.exit(7)'",
        }
    )

    assert result.success is False
    assert result.error == "命令退出码非零: 7"
    assert result.data["returncode"] == 7


@pytest.mark.anyio
async def test_shell_exec_truncates_stdout(tmp_path):
    tool = ShellExecTool(workspace_root=tmp_path)
    tool.max_output_chars = 20

    result = await tool.arun(
        {
            "command": "python -c 'print(\"x\" * 80)'",
        }
    )

    assert result.success is True
    assert result.content.endswith("truncated 60 chars")
    assert result.data["stdout"].endswith("truncated 61 chars")


@pytest.mark.anyio
async def test_shell_exec_rejects_dangerous_commands(tmp_path):
    result = await ShellExecTool(workspace_root=tmp_path).arun(
        {
            "command": "rm -rf target",
        }
    )

    assert result.success is False
    assert result.error == "危险命令被拒绝"


def test_create_tool_registry_passes_workspace_to_shell_exec(tmp_path):
    registry = create_tool_registry(workspace_root=tmp_path)
    tool = registry.require("shell_exec")

    assert isinstance(tool, ShellExecTool)
    assert tool.workspace_root == tmp_path.resolve()
