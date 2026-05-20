# agent-runtime

一个轻量的 Agent Runtime 项目，提供可治理的 Intent/Operation 执行系统与事件流式输出，并内置 CLI 方便本地交互调试。项目采用标准 src layout，支持
editable install 和全局命令 `agent`，可在任意目录直接启动。

## 主要能力

- 统一的运行时编排（Agent + Executor + Runtime）
- Operation 注册、Intent 解析与 Policy 校验
- 内置 Operation 集（文件系统、受限 shell、响应输出）
- 事件流式输出（Thought / Intent / Operation / Observation / FinalResult 等）
- 标准化包结构，便于扩展与发布

## 架构说明

项目核心围绕“任务输入 → 决策 → Intent Plan → Operation 解析 → Policy 校验 → 执行 → 事件输出”的闭环运行：

1. **AgentRuntime**（`agent_runtime.core.runtime`）负责串联整体流程，接受任务输入并驱动执行。
2. **Agent**（`agent_runtime.core.agent`）负责与 LLM 交互并生成 `IntentPlan`，不选择具体执行实现。
3. **OperationResolver**（`agent_runtime.operation.resolver`）把 `IntentRequest` 解析为确定性 `Operation`。
4. **PolicyEngine**（`agent_runtime.policy.engine`）在执行前拦截高风险或可被专用 intent 替代的通用入口。
5. **Executor**（`agent_runtime.core.executor`）只执行通过策略校验的 Operation，返回 Observation 事件。
6. **OperationRegistry**（`agent_runtime.operation.registry`）统一管理 Operation 注册、按 intent 查找、标签分类与扩展注入。
7. **Schema**（`agent_runtime.schema.*`）定义了事件与状态的结构，保证事件流可序列化且稳定。
8. **Observability**（`agent_runtime.observability.*`）提供基础追踪能力，便于定位执行链路。
9. **Memory/LLM**（`agent_runtime.memory` / `agent_runtime.llm`）提供可插拔能力，方便替换或扩展。

LLM 只生成意图，不直接选择 Operation：

```json
{
  "intent": "filesystem.read",
  "target": {
    "path": "xxx"
  },
  "params": {},
  "purpose": "需要读取文件分析结构"
}
```

Runtime 会将该 intent 解析为 `read_file` Operation。`shell.exec` 被建模为高风险通用 Operation，默认不会替代 `filesystem.read`、`filesystem.list`、`filesystem.write` 等专用 intent。

事件流的典型顺序：

```
Thought -> Intent -> Operation -> Observation (可能多轮) -> FinalResult
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
        ├── operation/
        ├── observability/
        ├── policy/
        └── schema/
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
