from __future__ import annotations


def test_root_public_api_exports_runtime_building_blocks():
    from agent_runtime import (
        Agent,
        AgentRuntime,
        BaseLLM,
        BaseTool,
        EventBus,
        Executor,
        JsonlTraceWriter,
        LLMConfigError,
        LLMProviderError,
        PolicyEngine,
        QwenLLM,
        ToolCall,
        ToolRegistry,
        create_tool_registry,
    )

    assert Agent.__name__ == "Agent"
    assert AgentRuntime.__name__ == "AgentRuntime"
    assert BaseLLM.__name__ == "BaseLLM"
    assert BaseTool.__name__ == "BaseTool"
    assert EventBus.__name__ == "EventBus"
    assert Executor.__name__ == "Executor"
    assert JsonlTraceWriter.__name__ == "JsonlTraceWriter"
    assert LLMConfigError.__name__ == "LLMConfigError"
    assert LLMProviderError.__name__ == "LLMProviderError"
    assert PolicyEngine.__name__ == "PolicyEngine"
    assert QwenLLM.__name__ == "QwenLLM"
    assert ToolCall.__name__ == "ToolCall"
    assert ToolRegistry.__name__ == "ToolRegistry"
    assert callable(create_tool_registry)


def test_subpackage_public_api_exports_expected_names():
    from agent_runtime import core, llm, schema, tool

    assert "AgentRuntime" in core.__all__
    assert "QwenLLM" in llm.__all__
    assert "ToolCall" in schema.__all__
    assert "ToolRegistry" in tool.__all__
