from typing import Dict, List, Optional, Sequence

from core.middleware import Pipeline, TraceMiddleware
from llm.base import BaseLLM, LLMResponse
from memory.base import MemoryStore
from observability.trace import TraceLogger
from schema.memory import MemoryItem
from schema.state import AgentState
from schema.step import Step
from tool.base import ToolResult
from tool.registry import ToolRegistry


class Executor:
    """Single-step executor for tool-using agents."""

    def __init__(
        self,
        llm: BaseLLM,
        tool_registry: ToolRegistry,
        memory: MemoryStore,
        *,
        pipeline: Optional[Pipeline] = None,
    ) -> None:
        self.llm = llm
        self.tools = tool_registry
        self.memory = memory
        self.pipeline = pipeline or Pipeline([TraceMiddleware()])

    def step(self, state: AgentState) -> Optional[ToolResult | str]:
        return self.pipeline.run(self._step_impl, state)

    def _step_impl(self, state: AgentState) -> Optional[ToolResult | str]:
        if state.done:
            return None
        if state.current_step >= state.max_steps:
            state.done = True
            TraceLogger.log("executor.stop", {"reason": "max_steps"})
            return "Reached max steps"

        response = self._call_llm(state)
        if response.content:
            self.memory.add(MemoryItem(role="assistant", content=response.content))

        if response.tool_calls:
            TraceLogger.log("executor.tool.calls", {"count": len(response.tool_calls)})
            result = self._handle_tool_calls(state, response)
            state.current_step += 1
            return result

        if response.content:
            state.done = True
            TraceLogger.log("executor.done", {"reason": "final_content"})
            return response.content

        return None

    def _call_llm(self, state: AgentState) -> LLMResponse:
        messages = self._build_messages(max_history=20)
        tools = self.tools.tool_schemas()
        TraceLogger.log("llm.request", {"messages": len(messages), "tools": len(tools)})
        response = self.llm.generate(messages=messages, tools=tools)
        TraceLogger.log(
            "llm.response",
            {
                "has_content": bool(response.content),
                "tool_calls": len(response.tool_calls),
                "finish_reason": response.finish_reason,
            },
        )
        return response

    def _handle_tool_calls(self, state: AgentState, response: LLMResponse) -> Optional[ToolResult]:
        last_result: Optional[ToolResult] = None
        for call in response.tool_calls:
            tool_input = call.arguments or {}
            result = self.tools.run(call.name, tool_input)
            last_result = result

            state.history.append(
                Step(tool=call.name, tool_input=tool_input, tool_output=result)
            )
            self.memory.add(
                MemoryItem(
                    role="tool",
                    content=result.content,
                    metadata={"tool": call.name},
                )
            )
        return last_result

    def _build_messages(self, max_history: int) -> List[Dict[str, str]]:
        items = self._tail(self.memory.recent(max_history), max_history)
        items = list(reversed(items))
        return [{"role": item.role, "content": item.content} for item in items]

    @staticmethod
    def _tail(items: Sequence[MemoryItem], limit: int) -> List[MemoryItem]:
        if limit <= 0:
            return []
        return list(items)[-limit:]
