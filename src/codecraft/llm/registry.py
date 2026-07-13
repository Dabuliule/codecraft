from __future__ import annotations

from codecraft.llm.base import LLMProvider


class LLMProviderRegistry:
    """按 provider name 管理可用的 LLMProvider。"""

    def __init__(self, providers: list[LLMProvider] | None = None) -> None:
        self._providers: dict[str, LLMProvider] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: LLMProvider) -> None:
        """注册一个 provider，并拒绝空名称或重复名称。"""
        name = provider.name.strip()
        if not name:
            raise ValueError("provider name must not be empty")
        if name in self._providers:
            raise ValueError(f"provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider:
        """按名称取 provider。"""
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"provider not registered: {name}") from exc
