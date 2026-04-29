from typing import Dict, List, Optional, Sequence

from llm.base import BaseLLM, LLMResponse
from memory.base import MemoryStore
from schema.memory import MemoryItem
from schema.state import AgentState
from schema.step import Step
from tool.base import ToolResult
from tool.registry import ToolRegistry


class Executor:
    """Single-step executor for tool-using agents."""

    def __init__(self, llm: BaseLLM, tool_registry: ToolRegistry, memory: MemoryStore) -> None:
        self.llm = llm
        self.tools = tool_registry
        self.memory = memory

    def step(self, state: AgentState) -> Optional[ToolResult | str]:
        if state.done:
            return None
        if state.current_step >= state.max_steps:
            state.done = True
            return "Reached max steps"

        response = self._call_llm()
        if response.content:
            self.memory.add(MemoryItem(role="assistant", content=response.content))

        if response.tool_calls:
            result = self._handle_tool_calls(state, response)
            state.current_step += 1
            return result

        if response.content:
            state.done = True
            return response.content

        return None

    def _call_llm(self) -> LLMResponse:
        messages = self._build_messages(max_history=20)
        tools = self.tools.tool_schemas()
        return self.llm.generate(messages=messages, tools=tools)

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
