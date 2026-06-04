from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from codecraft.core.errors import CodecraftError
from codecraft.core.turn_context import TurnContext
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.tool import ToolCall, ToolResult
from codecraft.tool.base import ToolContext
from codecraft.tool.registry import ToolRegistry


@dataclass(frozen=True)
class ToolRunnerEvent:
    type: RuntimeEventType
    payload: dict


class ToolRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def run(
        self,
        call: ToolCall,
        context: TurnContext,
    ) -> AsyncIterator[ToolRunnerEvent]:
        yield ToolRunnerEvent(
            RuntimeEventType.TOOL_CALL_STARTED,
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            },
        )

        started_at = monotonic()
        result: ToolResult
        try:
            tool = self.registry.get(call.name)
            args = tool.args_schema.model_validate(call.arguments)
            result = await tool.arun(args, ToolContext(context=context, call=call))
        except ValidationError as exc:
            result = ToolResult(
                success=False,
                content="Tool argument validation failed.",
                error=str(exc),
                suggestion="Check the tool schema and retry with valid arguments.",
            )
        except CodecraftError as exc:
            result = ToolResult(
                success=False,
                content=exc.message,
                error=exc.code,
                suggestion=exc.suggestion,
                metadata=exc.metadata,
            )
        except Exception as exc:
            result = ToolResult(
                success=False,
                content="Tool execution failed.",
                error=str(exc),
                suggestion="Check the tool arguments, workspace permissions, or runtime environment.",
            )

        yield ToolRunnerEvent(
            RuntimeEventType.TOOL_CALL_FINISHED,
            {
                "call_id": call.call_id,
                "name": call.name,
                "result": result.model_dump(mode="json"),
                "duration_ms": int((monotonic() - started_at) * 1000),
            },
        )
