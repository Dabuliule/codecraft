from __future__ import annotations

import pytest
from rich.console import Console

from codecraft.cli.rich_renderer import RichRenderer
from codecraft.schema.event import (
    ApprovalDecisionEvent,
    ApprovalRequestEvent,
    ObservationEvent,
    ToolCallEvent,
    ToolExecutionEvent,
)


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


@pytest.mark.anyio
async def test_rich_renderer_displays_approval_request_and_decision():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console)

    await renderer.handle(
        ApprovalRequestEvent(
            approval_id="approval-1",
            tool="shell_exec",
            args={"command": "python -V"},
            reason="shell_exec needs approval",
        )
    )
    await renderer.handle(
        ApprovalDecisionEvent(
            approval_id="approval-1",
            tool="shell_exec",
            approved=True,
            reason="approved by user",
        )
    )

    output = console.export_text()

    assert "approval required: shell_exec python -V" in output
    assert "tool: shell_exec" not in output
    assert "command: python -V" not in output
    assert "reason:" not in output
    assert "approved" in output


@pytest.mark.anyio
async def test_rich_renderer_hides_final_answer_tool_call_in_friendly_mode():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console)

    await renderer.handle(
        ToolCallEvent(
            tool="final_answer",
            args={"answer": "done"},
        )
    )

    output = console.export_text()

    assert output == ""


@pytest.mark.anyio
async def test_rich_renderer_displays_approval_reason_in_verbose_mode():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console, verbose=True)

    await renderer.handle(
        ApprovalRequestEvent(
            approval_id="approval-1",
            tool="shell_exec",
            args={"command": "python -V"},
            reason="shell_exec needs approval",
        )
    )

    output = console.export_text()

    assert "reason: shell_exec needs approval" in output
