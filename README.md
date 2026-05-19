# agent-runtime

一个轻量的 Agent Runtime 项目，提供可扩展的工具系统与事件流式输出，并内置 CLI 方便本地交互调试。项目采用标准 src layout，支持
editable install 和全局命令 `agent`，可在任意目录直接启动。

## 主要能力

- 统一的运行时编排（Agent + Executor + Runtime）
- 工具注册与内置工具集（文件系统、命令执行、响应输出）
- 事件流式输出（Thought / Action / Observation / FinalResult 等）
- 标准化包结构，便于扩展与发布

## 架构说明

项目核心围绕“任务输入 → 决策 → 工具执行 → 事件输出”的闭环运行：

1. **AgentRuntime**（`agent_runtime.core.runtime`）负责串联整体流程，接受任务输入并驱动执行。
2. **Agent**（`agent_runtime.core.agent`）负责与 LLM 交互并做决策，产出 Thought/Action/Final 等事件。
3. **Executor**（`agent_runtime.core.executor`）根据 Action 调度工具执行，返回 Observation 事件。
4. **ToolRegistry**（`agent_runtime.tool.registry`）统一管理工具的注册、查找与调用。
5. **Schema**（`agent_runtime.schema.*`）定义了事件与状态的结构，保证事件流可序列化且稳定。
6. **Observability**（`agent_runtime.observability.*`）提供基础追踪能力，便于定位执行链路。
7. **Memory/LLM**（`agent_runtime.memory` / `agent_runtime.llm`）提供可插拔能力，方便替换或扩展。

事件流的典型顺序：

```
Thought -> Action -> Observation (可能多轮) -> FinalResult
```

## 环境要求

- Python >= 3.11

## 项目结构

```
project_root/
├── pyproject.toml
├── README.md
└── src/
    └── agent_runtime/
        ├── cli/
        ├── core/
        ├── llm/
        ├── memory/
        ├── observability/
        ├── schema/
        └── tool/
```

## 安装（editable）

```zsh
uv pip install -e .
```

## 使用方式（CLI）

```zsh
agent
```

说明：

- CLI 会自动加载同目录下的 `.env`（如果存在）。
- 输入 `exit` 或 `quit` 退出。

