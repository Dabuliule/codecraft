from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
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
from codecraft.tool.observer import ToolResultObserver
from codecraft.tool.registry import ToolRegistry


@dataclass(frozen=True)
class ToolRunnerEvent:
    type: RuntimeEventType
    payload: dict


class ToolRunner:
    """统一执行 tool call，并把执行过程转成 RuntimeEvent。

    调用顺序是：参数 schema 校验、sandbox effect 检查、approval 检查、真正
    执行 tool。每一步失败都会变成 ToolResult，而不是让异常直接穿透到 turn。
    """

    def __init__(
        self,
        registry: ToolRegistry,
        approval_manager: ApprovalManager | None = None,
        observers: Sequence[ToolResultObserver] | None = None,
    ) -> None:
        self.registry = registry
        self.approval_manager = approval_manager or ApprovalManager()
        self.observers = tuple(observers or ())
        names = [observer.name for observer in self.observers]
        if len(names) != len(set(names)):
            raise ValueError("tool result observers must have unique names")

    async def run(
        self,
        call: ToolCall,
        context: TurnContext,
    ) -> AsyncIterator[ToolRunnerEvent]:
        """运行一个 tool call，并按执行阶段产出事件。"""
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
                # sandbox 是硬边界；不进入 approval，也不执行 tool。
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
                # approval 是可交互边界，通常由 UI 把请求展示给用户处理。
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
                args,
                ToolContext(
                    context=context,
                    call=call,
                    approved=approved,
                    command_decision=evaluation.command_decision,
                ),
            )
        except ValidationError as exc:
            result = ToolResult(
                success=False,
                content="Tool argument validation failed.",
                error="invalid_tool_arguments",
                suggestion="Check the tool schema and retry with valid arguments.",
                metadata={
                    "validation_errors": [
                        {
                            "location": ".".join(str(part) for part in error["loc"]),
                            "message": error["msg"],
                            "type": error["type"],
                        }
                        for error in exc.errors(include_url=False, include_input=False)
                    ]
                },
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
                error="tool_execution_error",
                suggestion="Check the tool arguments, workspace permissions, or runtime environment.",
                metadata={"exception_type": type(exc).__name__},
            )

        if result.success and self.observers:
            post_actions = await self._run_observers(call, result, context)
            if post_actions:
                result.metadata["post_actions"] = post_actions

        result = self._limit_output(result, context.max_tool_output_chars)
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

        for runtime_event in result.runtime_events:
            yield ToolRunnerEvent(
                runtime_event.type,
                {"call_id": call.call_id, **runtime_event.payload},
            )

    async def _run_observers(
        self,
        call: ToolCall,
        result: ToolResult,
        context: TurnContext,
    ) -> dict:
        actions = {}
        for observer in self.observers:
            try:
                details = await observer.after_result(call, result, context)
            except Exception as exc:
                details = {
                    "status": "failed",
                    "error": "observer_error",
                    "exception_type": type(exc).__name__,
                }
            if details is not None:
                actions[observer.name] = details
        return actions

    @staticmethod
    def _sandbox_policy(context: TurnContext) -> SandboxPolicy:
        return SandboxPolicy(
            mode=context.sandbox_mode,
            workspace_roots=context.workspace_roots,
            network_access=context.network_access,
        )

    @staticmethod
    def _limit_output(result: ToolResult, max_chars: int) -> ToolResult:
        if len(result.content) <= max_chars:
            return result
        return result.model_copy(
            update={
                "content": result.content[:max_chars],
                "metadata": {
                    **result.metadata,
                    "content_truncated": True,
                    "original_content_chars": len(result.content),
                },
            }
        )
