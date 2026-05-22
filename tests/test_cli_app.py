from __future__ import annotations

from typer.testing import CliRunner

from agent_runtime.cli.app import app


def test_trace_summary_command_accepts_trace_file_path(tmp_path):
    trace_path = tmp_path / "trace-1.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                '{"type":"thought","trace_id":"trace-1","thought":"inspect"}',
                '{"type":"final_result","trace_id":"trace-1","result":{"answer":"done"}}',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["trace-summary", str(trace_path)])

    assert result.exit_code == 0
    assert "trace_id: trace-1" in result.output
    assert "events: 2" in result.output
    assert "final_result=1" in result.output
    assert "final_answer: done" in result.output


def test_trace_summary_command_accepts_trace_id(tmp_path):
    trace_path = tmp_path / "trace-2.jsonl"
    trace_path.write_text(
        '{"type":"thought","trace_id":"trace-2","thought":"inspect"}\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "trace-summary",
            "trace-2",
            "--trace-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "trace_id: trace-2" in result.output
    assert "events: 1" in result.output
    assert "thought=1" in result.output
