from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter

from codecraft.llm.base import BaseLLM
from codecraft.schema.decision import Decision
from codecraft.schema.state import AgentState
from codecraft.tool.registry import ToolRegistry


class Agent:
    """
    单 Agent 决策器。

    职责：
    - 理解当前 runtime state
    - 维护整体执行方向
    - 生成 tool plan
    - 根据 observation 持续调整策略

    注意：
    - runtime 负责调度执行 plan
    - 每轮执行后基于 observation 重新生成后续 plan
    """

    def __init__(
            self,
            llm: BaseLLM,
            tool_registry: ToolRegistry,
    ) -> None:
        self.llm = llm
        self.tool_registry = tool_registry

        self.decision_adapter = TypeAdapter(Decision)

    async def astep(
            self,
            state: AgentState,
    ) -> Decision:

        messages = self._build_messages(state)

        response = await self.llm.agenerate(
            messages=messages,
            response_format={"type": "json_object"},
        )

        if not response.content:
            raise RuntimeError("Agent 返回为空")

        try:
            data = json.loads(response.content)

        except Exception as e:
            raise RuntimeError(
                f"Agent 输出非法 JSON:\n{response.content}"
            ) from e

        try:
            return self.decision_adapter.validate_python(data)

        except Exception as e:
            raise RuntimeError(
                f"Agent 输出不符合 Decision schema:\n{response.content}"
            ) from e

    def _build_messages(
            self,
            state: AgentState,
    ) -> list[dict[str, Any]]:

        tool_prompt = self._build_tool_prompt()

        recent_steps = self._build_recent_steps(state)

        memory_prompt = self._build_memory_prompt(state)

        schema_prompt = json.dumps(
            Decision.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = f"""
你是一个自主 Agent。

你的职责：

1. 理解当前任务
2. 基于当前状态生成 tool plan
3. 持续调整执行策略
4. 输出 tool plan，由 runtime 校验并调度执行
5. plan 执行后必须重新观察状态
6. 当任务完成时调用 final_answer 工具

plan 只能使用可用工具中的 tool 名称，并提供 args 和 purpose。
如果存在专用工具，不要使用 shell_exec。

你必须保持：

- grounded
- reactive
- incremental

# 当前任务

{state.task}

# 当前策略

目标:
{state.strategy.objective}

当前 focus:
{state.strategy.current_focus}

当前 approach:
{state.strategy.approach}

# 已发现事实

{memory_prompt}

# 最近执行步骤

{recent_steps}

# 可用 tools

{tool_prompt}

# 输出要求

严格输出 JSON。

不要 markdown。
不要解释。
不要输出 schema 之外的字段。

输出必须符合以下 schema：

{schema_prompt}
"""

        return [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

    def _build_tool_prompt(self) -> str:

        lines = []

        for tool in self.tool_registry.list_tools():
            schema = tool.tool_schema()

            lines.append(
                json.dumps(
                    schema,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        return "\n\n".join(lines)

    @staticmethod
    def _build_recent_steps(
            state: AgentState,
    ) -> str:

        if not state.recent_steps:
            return "暂无执行记录"

        lines = []

        for idx, step in enumerate(state.recent_steps[-6:], start=1):
            lines.append(
                f"""
步骤 {idx}

Thought:
{step.thought}

Tool:
{step.tool_call.tool}

Args:
{json.dumps(step.tool_call.args, ensure_ascii=False)}

Observation:
{str(step.observation)[:1500]}

Summary:
{step.summary}
"""
            )

        return "\n".join(lines)

    @staticmethod
    def _build_memory_prompt(
            state: AgentState,
    ) -> str:

        if not state.memory:
            return "暂无长期记忆"

        return "\n".join(
            f"- {m}"
            for m in state.memory
        )
