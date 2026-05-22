# agent-runtime

`agent-runtime` 是一个轻量级 Agent Runtime 原型，重点不在封装某个大模型接口，而在把 Agent 执行过程拆成可治理、可观察、可扩展的运行时闭环。

项目围绕一个核心问题展开：

> 当 LLM 需要调用本地工具完成任务时，Runtime 如何接管工具调度、策略校验、事件输出和执行轨迹，而不是把所有风险都交给模型自由发挥？

当前版本已经实现了单 Agent 的 step loop、Tool 注册与解析、执行前 Policy 校验、事件流式输出、CLI 交互和基础测试。后续会继续补强权限审批、工作目录沙箱、端到端测试、trace 持久化和更多 provider。

## 当前能力

- **Step-based Agent loop**：每轮由 Agent 基于当前 `AgentState` 生成 `Decision`，Runtime 调度工具并把结果写回状态。
- **Tool abstraction**：通过 `BaseTool` 统一工具 schema、参数校验、timeout、retry、异常归一化和返回格式。
- **Tool provider / registry**：工具由 `ToolProvider` 暴露，`ToolRegistry` 负责注册、按名称查找和按 tag 分类。
- **Policy check before execution**：`Executor` 在执行工具前调用 `PolicyEngine`，目前已将 `shell_exec` 建模为高风险通用入口。
- **Workspace-constrained filesystem**：内置文件系统工具会把路径解析到 workspace 内，拒绝 `..` 或绝对路径逃逸。
- **Streaming runtime events**：运行时输出 `thought`、`tool_call`、`tool_execution`、`observation`、`final_result` 等事件。
- **JSONL trace output**：CLI 运行时会把 RuntimeEvent 写入 `.agent-runtime/traces/{trace_id}.jsonl`，并支持 `/trace` 查看当前摘要。
- **CLI interaction**：提供 `agent` 命令，支持 Rich 渲染、verbose 模式和 `/status`、`/history` 等 slash command。
- **Pluggable LLM layer**：当前提供 Qwen/OpenAI-compatible provider，后续计划补充 mock provider 和更多模型适配。

## 架构总览

```text
User Task
   |
   v
AgentRuntime
   |
   | builds / updates AgentState
   v
Agent
   |
   | LLM returns Decision(JSON)
   v
ToolPlan
   |
   v
ToolResolver -----> ToolRegistry -----> ToolProvider
   |
   v
PolicyEngine
   |
   v
Executor
   |
   v
BaseTool.arun()
   |
   v
ToolResult
   |
   v
Runtime Events + Step History + Memory
```

更详细的设计说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 执行流程

一次任务的典型执行顺序如下：

1. 用户通过 CLI 输入任务。
2. `AgentRuntime` 初始化 `AgentState`，包含任务目标、策略、历史步骤和压缩记忆。
3. `Agent` 将当前状态、可用工具 schema 和输出 schema 组装成 prompt。
4. LLM 返回结构化 `Decision`，其中包含 `thought` 和 `ToolPlan`。
5. Runtime 依次发出 `ThoughtEvent` 和 `ToolCallEvent`。
6. `Executor` 使用 `ToolResolver` 将 `ToolCall` 解析为确定工具和参数。
7. `PolicyEngine` 在工具执行前进行策略校验。
8. 通过校验后，`BaseTool.arun()` 负责参数校验、timeout、retry 和异常归一化。
9. Runtime 将 `ToolResult` 记录为 `Step`，发出 `ObservationEvent`。
10. 如果工具是 `final_answer`，Runtime 生成 `AgentResult` 并发出 `FinalResultEvent`。

事件顺序通常是：

```text
Thought -> ToolCall -> ToolExecution -> Observation -> ... -> FinalResult
```

## 内置工具

| Tool | 作用 | 操作类型 | 风险级别 |
| --- | --- | --- | --- |
| `read_file` | 读取本地文件 | read | low |
| `write_file` | 写入或追加文件 | write | medium |
| `delete_file` | 删除文件 | write / delete | medium |
| `file_exists` | 检查路径是否存在 | read | low |
| `list_dir` | 列出目录内容 | read | low |
| `make_dir` | 创建目录 | write | medium |
| `final_answer` | 输出最终回答 | response | low |
| `shell_exec` | 通用 shell 入口 | generic | high |

当前策略下，`shell_exec` 默认不会直接执行；如果已有专用工具能满足需求，例如 `cat`、`ls`、`mkdir`、`rm`，Policy 会建议改用对应专用工具。

CLI 使用时，文件系统工具默认以启动 `agent` 命令时的当前目录作为 workspace，用户不需要额外配置。程序化嵌入 Runtime 时，也可以显式传入 workspace：

```python
from agent_runtime import create_tool_registry


registry = create_tool_registry(workspace_root="/path/to/project")
```

## 目录结构

```text
.
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── pyproject.toml
├── src/
│   └── agent_runtime/
│       ├── cli/          # CLI、Rich 渲染、slash command
│       ├── core/         # Runtime、Agent、Executor、EventBus
│       ├── llm/          # LLM 抽象与 provider
│       ├── policy/       # 执行前策略校验
│       ├── schema/       # Decision、State、Step、Event、Result
│       └── tool/         # Tool 抽象、注册、解析、内置工具
└── tests/
    ├── test_event_bus.py
    ├── test_rich_renderer.py
    ├── test_slash.py
    └── test_tool_registry.py
```

## 安装

项目使用 Python 3.11+，推荐通过 `uv` 创建环境并 editable install。

```zsh
uv pip install -e .
```

配置环境变量：

```zsh
cp .env.example .env
```

`.env` 中需要配置：

```text
DASHSCOPE_API_KEY=your_api_key
QWEN_MODEL=your_model_name
```

如果缺少上述配置，CLI 会在启动 provider 时给出明确错误提示。

## 使用

启动 CLI：

```zsh
agent
```

或直接运行：

```zsh
uv run agent
```

常用命令：

| 命令 | 说明 |
| --- | --- |
| `/help` | 查看 CLI 命令 |
| `/status` | 查看当前 runtime state 摘要 |
| `/history` | 查看最近 step 轨迹 |
| `/trace` | 查看当前 trace 文件摘要 |
| `/verbose` | 切换详细事件输出 |
| `/exit` | 退出 |

离线查看 trace 摘要：

```zsh
uv run agent trace-summary .agent-runtime/traces/<trace_id>.jsonl
uv run agent trace-summary <trace_id>
```

## 测试与质量检查

```zsh
uv run pytest
uv run ruff check .
```

当前测试覆盖：

- `EventBus` 异步事件分发顺序
- `ToolRegistry` provider 注册、重复工具名校验、内置工具注册
- CLI slash command 行为
- Rich renderer 输出截断与 JSON 展示
- JSONL trace 写入与 `/trace` 摘要

待补强测试：

- trace replay / summary 命令的端到端测试
- 稳定 demo 的回归测试

## 设计重点

### Runtime owns orchestration

LLM 只负责生成结构化 `Decision`，不直接执行工具。Runtime 是唯一调度者，负责状态管理、策略校验、工具执行和事件输出。

### Tool is deterministic capability

Tool 被建模为确定性执行单元，必须声明输入 schema、风险级别、前置条件、副作用和 tag。这样 Runtime 可以在执行前进行治理，而不是让 Agent 自由调用任意函数。

### Policy before execution

所有工具调用都必须经过 `Executor`，再由 `PolicyEngine` 判断是否允许。当前版本已经把 `shell_exec` 作为 high risk generic tool，后续会加入路径沙箱、审批流和权限级别。

### Events as integration boundary

Runtime 不直接绑定某种 UI。CLI 只是订阅事件的一种 consumer。后续可以把同一套事件流接到 Web UI、trace viewer、日志系统或测试断言中。

## 项目定位

这个项目不是 LangChain 的替代品，也不是一个完整生产级 Agent 平台。当前定位是：

- 学习和展示 Agent Runtime 的核心工程拆分
- 验证工具治理、事件流和状态闭环的设计
- 为后续扩展沙箱、审批、trace 和多 provider 打基础

和直接调用 LLM function calling 相比，本项目更关注：

- 工具执行权属于 Runtime，而不是模型
- 策略校验独立于 Tool 实现
- 每一步都有结构化事件和 step 记录
- Tool 能被 provider 化注册和治理

## Roadmap

详细计划见 [docs/ROADMAP.md](docs/ROADMAP.md)。近期优先级：

1. 补 Runtime 端到端测试和 Policy 测试。
2. 增加 approval decision，区分 allow / deny / require approval。
3. 增加 mock LLM provider，降低本地测试对真实模型的依赖。
4. 补充 trace 持久化和可回放能力。
5. 准备稳定 demo 和示例输出。
