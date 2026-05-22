from __future__ import annotations

import pytest
from rich.console import Console

from agent_runtime.cli.rich_renderer import RichRenderer
from agent_runtime.schema.event import ObservationEvent, ToolExecutionEvent


@pytest.mark.anyio
async def test_rich_renderer_truncates_long_observation_output():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console, max_output_chars=20)

    await renderer.handle(
        ObservationEvent(
            content="x" * 80,
            success=False,
        )
    )

    output = console.export_text()

    assert "truncated" in output


@pytest.mark.anyio
async def test_rich_renderer_displays_tool_input_as_json():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console, verbose=True)

    await renderer.handle(
        ToolExecutionEvent(
            tool="read_file",
            tool_input={"path": "README.md"},
        )
    )

    output = console.export_text()

    assert "run: read_file" in output
    assert '"path": "README.md"' in output


@pytest.mark.anyio
async def test_rich_renderer_displays_approval_required_observation():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console)

    await renderer.handle(
        ObservationEvent(
            content="",
            success=False,
            error="shell_exec 是高风险通用 Tool，默认需要外部审批",
            data={
                "policy": {
                    "action": "require_approval",
                    "reason": "shell_exec 是高风险通用 Tool，默认需要外部审批",
                    "data": {
                        "tool": "shell_exec",
                        "risk_level": "high",
                    },
                }
            },
        )
    )

    output = console.export_text()

    assert "approval required" in output
    assert "error: shell_exec 是高风险通用 Tool，默认需要外部审批" in output
