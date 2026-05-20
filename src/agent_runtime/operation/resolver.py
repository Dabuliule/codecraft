from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agent_runtime.operation.base import BaseOperation
from agent_runtime.operation.registry import OperationRegistry
from agent_runtime.schema.intent import IntentRequest


@dataclass(frozen=True)
class ResolvedOperation:
    intent: IntentRequest
    operation: BaseOperation
    args: Dict[str, Any]


class OperationResolver:
    """将 IntentRequest 解析为确定性 Operation。"""

    def __init__(self, registry: OperationRegistry) -> None:
        self.registry = registry

    def resolve(self, request: IntentRequest) -> ResolvedOperation:
        operation = self.registry.get_by_intent(request.intent)
        if operation is None:
            raise ValueError(f"未找到可处理 intent 的 Operation: {request.intent}")

        return ResolvedOperation(
            intent=request,
            operation=operation,
            args=operation.build_args(request),
        )
