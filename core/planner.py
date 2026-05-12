from __future__ import annotations

import json
from typing import Any, Dict, List

from llm.base import BaseLLM
from schema.state import AgentState
from schema.step import Step
from tool.registry import ToolRegistry


class Planner:
    """负责根据当前 state 生成下一步执行计划。"""

    def __init__(
            self,
            llm: BaseLLM,
            tool_registry: ToolRegistry,
    ):
        self.llm = llm
        self.tool_registry = tool_registry

    async def aplan(
            self,
            state: AgentState,
    ) -> List[Step]:

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
            raise RuntimeError(f"Planner 输出非法 JSON:\n{response.content}") from e

        raw_steps = data.get("steps", [])

        steps: List[Step] = []

        for raw_step in raw_steps:
            step = Step(
                tool=raw_step["tool"],
                tool_input=raw_step.get("tool_input", {}),
                tool_output=None,
                metadata={
                    "reason": raw_step.get("reason"),
                    "planner_raw": raw_step,
                },
            )

            steps.append(step)

        return steps

    def _build_messages(
            self,
            state: AgentState,
    ) -> List[Dict[str, Any]]:

        tool_prompt = self._build_tool_prompt()

        history_prompt = self._build_history_prompt(state)

        system_prompt = f"""
你是一个 Agent Planner。

你的职责：

1. 分析用户任务
2. 决定下一步需要调用哪些工具
3. 生成执行步骤
4. 不要直接回答用户
5. 不要执行工具
6. 只输出 JSON

你可以使用如下工具：

{tool_prompt}

当前执行历史：

{history_prompt}

输出格式：

{{
  "steps": [
    {{
      "tool": "工具名",
      "tool_input": {{
        "参数名": "参数值"
      }},
      "reason": "为什么调用该工具"
    }}
  ]
}}

规则：

- 只输出 JSON
- 不要 markdown
- 不要解释
- 如果任务已经完成，返回:
{{
  "steps": []
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
            lines.append(
                f"""
步骤 {idx + 1}

工具:
{step.tool}

输入:
{json.dumps(step.tool_input, ensure_ascii=False)}

输出:
{json.dumps(step.tool_output.model_dump(), ensure_ascii=False)}

元数据:
{json.dumps(step.metadata, ensure_ascii=False)}
"""
            )

        return "\n".join(lines)
