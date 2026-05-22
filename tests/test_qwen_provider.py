from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_runtime.llm.base import LLMConfigError, LLMProviderError
from agent_runtime.llm.providers.qwen import QwenLLM


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


def make_response(content: str = "ok"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=2,
        ),
    )


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


@pytest.mark.anyio
async def test_qwen_provider_retries_completion_failures(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    llm = QwenLLM(
        model="qwen-test",
        api_key="test-key",
        max_retries=1,
        retry_delay_seconds=0,
    )
    fake_client = FakeClient(
        outcomes=[
            RuntimeError("temporary failure"),
            make_response("done"),
        ]
    )
    llm.client = fake_client

    response = await llm.agenerate(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "done"
    assert response.usage == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
    }
    assert fake_client.completions.calls == 2


@pytest.mark.anyio
async def test_qwen_provider_wraps_completion_failures(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    llm = QwenLLM(
        model="qwen-test",
        api_key="test-key",
        max_retries=1,
        retry_delay_seconds=0,
    )
    fake_client = FakeClient(
        outcomes=[
            RuntimeError("first failure"),
            RuntimeError("second failure"),
        ]
    )
    llm.client = fake_client

    with pytest.raises(LLMProviderError, match="after 2 attempt"):
        await llm.agenerate(messages=[{"role": "user", "content": "hi"}])

    assert fake_client.completions.calls == 2


@pytest.mark.anyio
async def test_qwen_provider_wraps_response_parse_failures(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    llm = QwenLLM(
        model="qwen-test",
        api_key="test-key",
        retry_delay_seconds=0,
    )
    llm.client = FakeClient(outcomes=[SimpleNamespace(choices=[])])

    with pytest.raises(LLMProviderError, match="response parsing failed"):
        await llm.agenerate(messages=[{"role": "user", "content": "hi"}])
