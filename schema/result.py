from pydantic import BaseModel


class AgentResult(BaseModel):
    success: bool
    answer: str | None = None

    def pretty(self) -> str:
        lines: list[str] = ["=" * 60, "AGENT RESULT", "=" * 60, f"Success : {self.success}"]

        if self.answer:
            lines.append("")
            lines.append("Answer:")
            lines.append(self.answer)

        return "\n".join(lines)
