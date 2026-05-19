from __future__ import annotations

from pydantic import BaseModel, Field

from agent_runtime.schema.step import Step


class AgentResult(BaseModel):
    """
    Agent Runtime 最终执行结果。
    """
    success: bool = Field(
        ...,
        description="任务是否成功完成",
    )

    answer: str | None = Field(
        default=None,
        description="最终回答",
    )

    steps: list[Step] = Field(
        default_factory=list,
        description="执行轨迹",
    )

    memory: list[str] = Field(
        default_factory=list,
        description="压缩后的长期记忆",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="运行时警告",
    )

    total_steps: int = Field(
        default=0,
        description="总执行步数",
    )

    def pretty(self) -> str:
        lines: list[str] = [
            "=" * 60,
            "AGENT RESULT",
            "=" * 60,
            f"Success     : {self.success}",
            f"Total Steps : {self.total_steps}",
        ]

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")

            for warning in self.warnings:
                lines.append(f"- {warning}")

        if self.memory:
            lines.append("")
            lines.append("Memory:")

            for item in self.memory:
                lines.append(f"- {item}")

        if self.answer:
            lines.append("")
            lines.append("Final Answer:")
            lines.append(self.answer)

        if self.steps:
            lines.append("")
            lines.append("=" * 60)
            lines.append("EXECUTION TRAJECTORY")
            lines.append("=" * 60)

            for idx, step in enumerate(self.steps, start=1):
                lines.append("")
                lines.append(f"[Step {idx}]")
                lines.append(step.pretty())

        return "\n".join(lines)
