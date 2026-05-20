from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IntentRequest(BaseModel):
    """
    LLM 输出的意图请求。

    Intent 只描述目标和目的，不指定具体执行实现。Runtime 会把 intent
    解析为 Operation，并在执行前进行策略校验。
    """

    intent: str = Field(description="意图名称，例如 filesystem.read")
    target: Dict[str, Any] = Field(default_factory=dict, description="意图作用目标")
    params: Dict[str, Any] = Field(default_factory=dict, description="执行参数")
    purpose: Optional[str] = Field(default=None, description="为什么需要该意图")

    def pretty(self) -> str:
        return (
            f"Intent: {self.intent}\n"
            f"Target:\n"
            f"{json.dumps(self.target, ensure_ascii=False, indent=2)}\n"
            f"Params:\n"
            f"{json.dumps(self.params, ensure_ascii=False, indent=2)}\n"
            f"Purpose: {self.purpose or '-'}"
        )


class IntentPlan(BaseModel):
    """Agent 生成、Runtime 负责解析和调度的意图计划。"""

    intents: list[IntentRequest] = Field(
        default_factory=list,
        description="按顺序处理的意图请求",
    )
