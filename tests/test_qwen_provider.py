from __future__ import annotations

import pytest

from agent_runtime.llm.providers.qwen import LLMConfigError, QwenLLM


def test_qwen_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen-test")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(LLMConfigError, match="DASHSCOPE_API_KEY"):
        QwenLLM()


def test_qwen_provider_requires_model(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.delenv("QWEN_MODEL", raising=False)

    with pytest.raises(LLMConfigError, match="QWEN_MODEL"):
        QwenLLM()


def test_qwen_provider_accepts_explicit_config(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)

    llm = QwenLLM(
        model="qwen-test",
        api_key="test-key",
    )

    assert llm.model == "qwen-test"
