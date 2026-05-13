from __future__ import annotations

import json
from typing import Any, Dict, List

from pydantic import TypeAdapter

from llm.base import BaseLLM
from schema.plan import Plan
from schema.state import AgentState
from tool.registry import ToolRegistry


class Planner:
    """负责根据当前 state 生成完整执行计划。"""

    def __init__(
            self,
            llm: BaseLLM,
            tool_registry: ToolRegistry,
    ):
        self.llm = llm
        self.tool_registry = tool_registry

        self.plan_adapter = TypeAdapter(Plan)

    async def aplan(
            self,
            state: AgentState,
    ) -> Plan:

        messages = self._build_messages(state)

        response = await self.llm.agenerate(
            messages=messages,
            response_format={"type": "json_object"},
        )

        if not response.content:
            raise RuntimeError("Planner 返回为空")

        try:
            data = json.loads(response.content)

        except Exception as e:
            raise RuntimeError(
                f"Planner 输出非法 JSON:\n{response.content}"
            ) from e

        try:
            return self.plan_adapter.validate_python(data)

        except Exception as e:
            raise RuntimeError(
                f"Planner 输出不符合 Plan schema:\n{response.content}"
            ) from e

    def _build_messages(
            self,
            state: AgentState,
    ) -> List[Dict[str, Any]]:

        tool_prompt = self._build_tool_prompt()

        history_prompt = self._build_history_prompt(state)

        schema_prompt = json.dumps(
            Plan.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )

        example_prompt = """
{
  "actions": [
    {
      "tool": "search",
      "tool_input": {
        "query": "RocksDB WAL"
      },
      "reason": "先搜索 RocksDB WAL 基本原理"
    }
  ]
}
"""

        system_prompt = f"""
你是一个 Agent Planner。

你的职责：

1. 分析用户任务
2. 生成完整执行计划
3. 决定需要调用哪些工具
4. 不要直接回答用户
5. 不要执行工具
6. 只输出 JSON

你可以使用如下工具：

{tool_prompt}

当前执行历史：

{history_prompt}

输出必须严格符合以下 JSON Schema：

{schema_prompt}

输出示例：

{example_prompt}

规则：

- 只输出 JSON
- 不要 markdown
- 不要解释
- actions 必须是数组
- tool 必须是提供的工具之一
- tool_input 必须符合工具 schema
- 如果任务已经完成，返回：

{{
  "actions": []
}}
"""

        return [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": state.task,
            },
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
    def _build_history_prompt(
            state: AgentState,
    ) -> str:

        if not state.history:
            return "暂无执行历史"

        lines = []

        for idx, step in enumerate(state.history):

            observation = step.observation

            if hasattr(observation, "model_dump"):
                observation = observation.model_dump()

            lines.append(
                f"""
步骤 {idx + 1}

工具:
{step.action.tool}

输入:
{json.dumps(step.action.tool_input, ensure_ascii=False)}

输出:
{json.dumps(observation, ensure_ascii=False)}
    
元数据:
{json.dumps(step.metadata, ensure_ascii=False)}
"""
            )

        return "\n".join(lines)
