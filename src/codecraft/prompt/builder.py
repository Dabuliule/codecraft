from __future__ import annotations

from dataclasses import dataclass, field

from codecraft.core.conversation import Conversation
from codecraft.core.turn_context import TurnContext
from codecraft.llm.messages import ModelMessage, ModelRole
from codecraft.prompt.base import BASE_INSTRUCTIONS
from codecraft.prompt.instructions import InstructionLoader
from codecraft.schema.session import SessionConfig


@dataclass(frozen=True)
class PromptBuilder:
    instruction_loader: InstructionLoader = field(default_factory=InstructionLoader)

    def build(
        self,
        *,
        config: SessionConfig,
        conversation: Conversation,
        context: TurnContext,
    ) -> list[ModelMessage]:
        sections = [
            ("base_instructions", config.base_instructions or BASE_INSTRUCTIONS),
            (
                "project_instructions",
                config.project_instructions
                or self.instruction_loader.load_project_instructions(
                    cwd=context.cwd,
                    workspace_roots=context.workspace_roots,
                ),
            ),
            ("user_instructions", config.user_instructions),
            ("turn_context", self._turn_context(context)),
        ]
        content = "\n\n".join(
            f"<{name}>\n{body.strip()}\n</{name}>"
            for name, body in sections
            if body and body.strip()
        )
        return [
            ModelMessage(role=ModelRole.SYSTEM, content=content),
            *conversation.build_model_messages(),
        ]

    @staticmethod
    def _turn_context(context: TurnContext) -> str:
        return "\n".join(
            [
                f"cwd: {context.cwd}",
                f"workspace_roots: {', '.join(str(root) for root in context.workspace_roots)}",
                f"approval_policy: {context.approval_policy}",
                f"sandbox_mode: {context.sandbox_mode}",
                f"network_access: {str(context.network_access).lower()}",
            ]
        )
