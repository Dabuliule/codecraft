from __future__ import annotations

from io import StringIO

from rich.console import Console

from codecraft.cli.ui.render_config import RenderConfig
from codecraft.cli.ui.console import CODECRAFT_THEME
from codecraft.cli.ui.tool_renderer import ToolRenderer


def test_read_file_renderer_shows_summary_without_file_content():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, width=120)
    renderer = ToolRenderer(console, RenderConfig())

    renderer.render_started(
        {
            "call_id": "call_read",
            "name": "read_file",
            "arguments": {"path": "src/codecraft/cli/app.py"},
        }
    )
    renderer.render_finished(
        {
            "call_id": "call_read",
            "name": "read_file",
            "duration_ms": 5,
            "result": {
                "success": True,
                "content": "SECRET FILE CONTENT\n" * 20,
                "data": {
                    "path": "/repo/src/codecraft/cli/app.py",
                    "line_count": 312,
                    "truncated": False,
                },
                "metadata": {
                    "path": "/repo/src/codecraft/cli/app.py",
                    "chars": 14600,
                    "returned_chars": 14600,
                    "truncated": False,
                },
            },
        }
    )

    output = stream.getvalue()
    assert "• read_file" in output
    assert "✓ read_file /repo/src/codecraft/cli/app.py · 312 lines · 14.6 KB" in output
    assert "SECRET FILE CONTENT" not in output
    assert "[tool] read_file" not in output


def test_workspace_search_renderer_shows_summary_and_preview():
    stream = StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        theme=CODECRAFT_THEME,
    )
    renderer = ToolRenderer(console, RenderConfig())

    renderer.render_started(
        {
            "call_id": "call_search",
            "name": "workspace_search",
            "arguments": {"query": "Agent"},
        }
    )
    renderer.render_finished(
        {
            "call_id": "call_search",
            "name": "workspace_search",
            "duration_ms": 3,
            "result": {
                "success": True,
                "content": "src/app.py:12: class Agent:\n",
                "data": {
                    "query": "Agent",
                    "match_count": 1,
                    "matches": [],
                    "truncated": False,
                },
                "metadata": {
                    "query": "Agent",
                    "match_count": 1,
                    "truncated": False,
                },
            },
        }
    )

    output = stream.getvalue()
    assert "• workspace_search Agent" in output
    assert "✓ workspace_search Agent · 1 matches · 3ms" in output
    assert "[tool] workspace_search ok (3ms): src/app.py:12: class Agent:" in output
