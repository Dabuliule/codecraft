from pydantic import BaseModel, Field

from schema import Step


class AgentResult(BaseModel):
    success: bool
    answer: str | None = None
    steps: list[Step] = Field(default_factory=list)

    def pretty(self) -> str:
        lines: list[str] = ["=" * 60, "AGENT RESULT", "=" * 60, f"Success : {self.success}"]

        if self.answer:
            lines.append("")
            lines.append("Answer:")
            lines.append(self.answer)

        if self.steps:
            lines.append("")
            lines.append(f"Steps ({len(self.steps)}):")

            for idx, step in enumerate(self.steps, start=1):
                lines.append("")
                lines.append(f"[{idx}] {step.pretty()}")

        return "\n".join(lines)