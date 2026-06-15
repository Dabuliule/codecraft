from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from codecraft.approval.manager import ApprovalManager
from codecraft.core.errors import CodecraftError
from codecraft.core.turn_context import TurnContext
from codecraft.sandbox.policy import SandboxPolicy
from codecraft.schema.event import RuntimeEventType
from codecraft.schema.tool import ToolCall, ToolResult
from codecraft.tool.base import ToolContext
from codecraft.tool.registry import ToolRegistry


@dataclass(frozen=True)
class ToolRunnerEvent:
    type: RuntimeEventType
    payload: dict


class ToolRunner:
    def __init__(
        self,
        registry: ToolRegistry,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self.registry = registry
        self.approval_manager = approval_manager or ApprovalManager()

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
        approved = False
        try:
            tool = self.registry.get(call.name)
            args = tool.args_schema.model_validate(call.arguments)
            sandbox_evaluation = self._sandbox_policy(context).evaluate_effects(
                tool.effects
            )
            if not sandbox_evaluation.allowed:
                result = ToolResult(
                    success=False,
                    content="Tool execution denied by sandbox policy.",
                    error="sandbox_denied",
                    suggestion=sandbox_evaluation.reason,
                    metadata={
                        "tool": call.name,
                        "sandbox_mode": context.sandbox_mode,
                        "denied_effect": sandbox_evaluation.denied_effect,
                    },
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
                return

            evaluation = await self.approval_manager.evaluate(tool, call, args, context)
            if evaluation.requires_approval:
                approval_request = self.approval_manager.build_request(
                    call=call,
                    context=context,
                    evaluation=evaluation,
                )
                yield ToolRunnerEvent(
                    RuntimeEventType.APPROVAL_REQUESTED,
                    approval_request.model_dump(mode="json"),
                )
                approval_decision = await self.approval_manager.request(
                    approval_request
                )
                yield ToolRunnerEvent(
                    RuntimeEventType.APPROVAL_DECIDED,
                    approval_decision.model_dump(mode="json"),
                )
                if not approval_decision.approved:
                    result = ToolResult(
                        success=False,
                        content="Tool execution denied by approval.",
                        error="approval_denied",
                        suggestion=approval_decision.reason,
                        metadata={
                            "approval_id": approval_decision.approval_id,
                            "tool": call.name,
                        },
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
                    return
                approved = True
            result = await tool.arun(
                args, ToolContext(context=context, call=call, approved=approved)
            )
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

        finished_payload = {
            "call_id": call.call_id,
            "name": call.name,
            "result": result.model_dump(mode="json"),
            "duration_ms": int((monotonic() - started_at) * 1000),
        }
        yield ToolRunnerEvent(
            RuntimeEventType.TOOL_CALL_FINISHED,
            finished_payload,
        )

        if call.name == "apply_patch" and result.success:
            yield ToolRunnerEvent(
                RuntimeEventType.PATCH_APPLIED,
                {
                    "call_id": call.call_id,
                    "changed_files": result.data.get("changed_files", [])
                    if result.data
                    else [],
                    "modified": result.data.get("modified", 0) if result.data else 0,
                    "added": result.data.get("added", 0) if result.data else 0,
                    "deleted": result.data.get("deleted", 0) if result.data else 0,
                },
            )

    @staticmethod
    def _sandbox_policy(context: TurnContext) -> SandboxPolicy:
        return SandboxPolicy(
            mode=context.sandbox_mode,
            workspace_roots=context.workspace_roots,
            network_access=context.network_access,
        )
