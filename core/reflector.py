import json
from typing import Any, Dict, List

from pydantic import TypeAdapter

from llm.base import BaseLLM
from schema.reflection import Reflection
from schema.state import AgentState


class Reflector:
    """Simple reflection step to decide whether to retry."""

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm
        self.reflection_adapter = TypeAdapter(Reflection)

    async def areflect(self, state: AgentState) -> Reflection:
        messages = self._build_messages(state)

        response = await self.llm.agenerate(
            messages=messages,
            response_format={"type": "json_object"},
        )

        if not response.content:
            raise RuntimeError("Reflector 返回为空")

        try:
            data = json.loads(response.content)

        except Exception as e:
            raise RuntimeError(
                f"Planner 输出非法 JSON:\n{response.content}"
            ) from e

        try:
            return self.reflection_adapter.validate_python(data)

        except Exception as e:
            raise RuntimeError(
                f"Planner 输出不符合 Plan schema:\n{response.content}"
            ) from e

    @staticmethod
    def _build_messages(state: AgentState) -> List[Dict[str, Any]]:
        trajectory = []

        schema_prompt = json.dumps(
            Reflection.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
        for i, step in enumerate(state.history):
            trajectory.append(
                f"""
        Step {i + 1}

        Action:
        {step.action}

        Observation:
        {step.observation}
        """
            )

        prompt = f"""
        你是一个 Agent Runtime 的 Reflector（反思器）。

        你的职责是评估当前 Agent 的执行轨迹（trajectory），判断任务是否正在有效推进。

        你需要基于：

        - 用户任务
        - 历史执行步骤
        - 工具调用结果

        分析当前执行状态，并决定 Runtime 下一步应该如何运行。

        用户任务：
        {state.task}

        执行历史：
        {chr(10).join(trajectory)}

        请重点判断：

        1. 当前任务是否已经完成
        2. 当前执行是否仍在有效推进
        3. 当前失败是否只需要重试
        4. 当前策略是否已经偏离目标，需要重新规划
        5. 当前任务是否已经无法继续执行

        输出必须严格符合以下 JSON Schema：
        {schema_prompt}

        请严格返回结构化 JSON。
        不要输出 Markdown。
        不要输出额外解释。
        """

        return [
            {
                "role": "user",
                "content": prompt
            }
        ]
