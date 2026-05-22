from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_runtime.schema.event import RuntimeEvent


@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    path: Path
    event_count: int
    event_counts: dict[str, int]
    last_event_type: str | None
    final_answer: str | None


class JsonlTraceWriter:
    """Persist runtime events as one JSON object per line."""

    def __init__(
            self,
            trace_dir: str | Path = ".agent-runtime/traces",
    ) -> None:
        self.trace_dir = Path(trace_dir)

    async def handle(
            self,
            event: RuntimeEvent,
    ) -> None:
        trace_id = event.trace_id or "unknown"
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        with self.trace_path(trace_id).open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def trace_path(
            self,
            trace_id: str,
    ) -> Path:
        return self.trace_dir / f"{trace_id}.jsonl"

    def summarize(
            self,
            trace_id: str,
    ) -> TraceSummary | None:
        path = self.trace_path(trace_id)
        if not path.exists():
            return None

        return self.summarize_path(
            path=path,
            trace_id=trace_id,
        )

    def summarize_ref(
            self,
            ref: str,
    ) -> TraceSummary | None:
        path = Path(ref)
        if path.exists():
            return self.summarize_path(path)

        return self.summarize(ref)

    @staticmethod
    def summarize_path(
            path: str | Path,
            trace_id: str | None = None,
    ) -> TraceSummary:
        path = Path(path)

        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                events.append(json.loads(text))

        counts = Counter(str(event.get("type", "unknown")) for event in events)
        last_event_type = str(events[-1].get("type")) if events else None

        final_answer = None
        for event in reversed(events):
            if event.get("type") != "final_result":
                continue
            result = event.get("result")
            if isinstance(result, dict):
                answer = result.get("answer")
                if isinstance(answer, str):
                    final_answer = answer
            break

        return TraceSummary(
            trace_id=trace_id or path.stem,
            path=path,
            event_count=len(events),
            event_counts=dict(sorted(counts.items())),
            last_event_type=last_event_type,
            final_answer=final_answer,
        )
