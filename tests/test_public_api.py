from __future__ import annotations


def test_root_public_api_exports_runtime_building_blocks():
    from codecraft import (
        Agent,
        AgentRuntime,
        ApprovalBroker,
        ApprovalGate,
        BaseLLM,
        BaseTool,
        EventBus,
        ToolExecutor,
        JsonlTraceWriter,
        LLMConfigError,
        LLMProviderError,
        PolicyEngine,
        QwenLLM,
        ToolCall,
        GuardedToolOutcome,
        ToolRegistry,
        create_tool_registry,
    )

    assert Agent.__name__ == "Agent"
    assert AgentRuntime.__name__ == "AgentRuntime"
    assert ApprovalBroker.__name__ == "ApprovalBroker"
    assert ApprovalGate.__name__ == "ApprovalGate"
    assert BaseLLM.__name__ == "BaseLLM"
    assert BaseTool.__name__ == "BaseTool"
    assert EventBus.__name__ == "EventBus"
    assert ToolExecutor.__name__ == "ToolExecutor"
    assert JsonlTraceWriter.__name__ == "JsonlTraceWriter"
    assert LLMConfigError.__name__ == "LLMConfigError"
    assert LLMProviderError.__name__ == "LLMProviderError"
    assert PolicyEngine.__name__ == "PolicyEngine"
    assert QwenLLM.__name__ == "QwenLLM"
    assert ToolCall.__name__ == "ToolCall"
    assert GuardedToolOutcome.__name__ == "GuardedToolOutcome"
    assert ToolRegistry.__name__ == "ToolRegistry"
    assert callable(create_tool_registry)


def test_subpackage_public_api_exports_expected_names():
    from codecraft import core, llm, schema, tool

    assert "AgentRuntime" in core.__all__
    assert "QwenLLM" in llm.__all__
    assert "ToolCall" in schema.__all__
    assert "ToolRegistry" in tool.__all__
