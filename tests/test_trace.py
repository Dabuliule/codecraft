from __future__ import annotations

import json

import pytest

from agent_runtime.core.trace import JsonlTraceWriter
from agent_runtime.schema.event import FinalResultEvent, ThoughtEvent
from agent_runtime.schema.result import AgentResult


@pytest.mark.anyio
async def test_jsonl_trace_writer_persists_events_by_trace_id(tmp_path):
    writer = JsonlTraceWriter(trace_dir=tmp_path)

    await writer.handle(
        ThoughtEvent(
            trace_id="trace-1",
            thought="inspect",
        )
    )
    await writer.handle(
        FinalResultEvent(
            trace_id="trace-1",
            result=AgentResult(
                success=True,
                answer="done",
                total_steps=1,
            ),
        )
    )

    path = tmp_path / "trace-1.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "thought"
    assert json.loads(lines[1])["result"]["answer"] == "done"

    summary = writer.summarize("trace-1")

    assert summary is not None
    assert summary.event_count == 2
    assert summary.event_counts == {
        "final_result": 1,
        "thought": 1,
    }
    assert summary.last_event_type == "final_result"
    assert summary.final_answer == "done"
