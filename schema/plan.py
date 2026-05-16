from pydantic import BaseModel, Field

from schema.action import ToolAction


class Plan(BaseModel):
    actions: list[ToolAction] = Field(default_factory=list, description="执行计划")

    def pretty(self) -> str:
        if not self.actions:
            return "📋 Plan(empty)"

        lines = ["📋 Execution Plan:"]

        for i, action in enumerate(self.actions, start=1):
            action_text = action.pretty()

            indented = "\n".join(
                "   " + line
                for line in action_text.splitlines()
            )

            lines.append(f"{i}.\n{indented}")

        return "\n\n".join(lines)
