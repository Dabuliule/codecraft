from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """工具调用请求（从 LLM 返回）"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """
    标准的 LLM 生成结果，屏蔽不同提供商的差异。
    Agent 只依赖这个结构，不依赖原始 OpenAI/Anthropic 对象。
    """
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None  # "stop", "tool_calls", "length", ...
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": ..., "completion_tokens": ...}


class BaseLLM(ABC):
    """
    所有 LLM 适配器的基类。
    子类只需要实现 `agenerate`，框架就会自动获得异步支持。
    """

    @abstractmethod
    async def agenerate(
            self,
            messages: List[Dict[str, Any]],
            tools: Optional[List[Dict[str, Any]]] = None,
            **kwargs: Any,
    ) -> LLMResponse:
        """
        异步生成回复。

        Args:
            messages: 消息列表，格式兼容 OpenAI 的 dict 形式。
            tools: 工具定义列表，兼容 OpenAI function calling 格式。
            **kwargs: 传递给具体模型的额外参数（如 temperature）。

        Returns:
            统一响应对象 LLMResponse。
        """
        ...

    def generate(
            self,
            messages: List[Dict[str, Any]],
            tools: Optional[List[Dict[str, Any]]] = None,
            **kwargs: Any,
    ) -> LLMResponse:
        """同步生成回复。

        注意：若当前线程已经在运行事件循环（如 Jupyter/FastAPI），
        请直接使用 `await agenerate(...)`。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.agenerate(messages=messages, tools=tools, **kwargs))

        raise RuntimeError(
            "检测到当前线程已有运行中的事件循环，请改用 `await llm.agenerate(...)`。"
        )
