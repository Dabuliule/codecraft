from __future__ import annotations

import pytest
from rich.console import Console

from agent_runtime.cli.rich_renderer import RichRenderer
from agent_runtime.schema.event import ObservationEvent, OperationEvent


@pytest.mark.anyio
async def test_rich_renderer_truncates_long_observation_output():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console, max_output_chars=20)

    await renderer.handle(
        ObservationEvent(
            content="x" * 80,
            success=True,
        )
    )

    output = console.export_text()

    assert "truncated" in output


@pytest.mark.anyio
async def test_rich_renderer_displays_tool_input_as_json():
    console = Console(record=True, width=100)
    renderer = RichRenderer(console=console)

    await renderer.handle(
        OperationEvent(
            operation="read_file",
            intent="filesystem.read",
            tool_input={"path": "README.md"},
        )
    )

    output = console.export_text()

    assert "Operation" in output
    assert '"path": "README.md"' in output
