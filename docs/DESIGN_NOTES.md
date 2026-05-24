# Design Notes

本文档记录 `CodeCraft` 当前已经落地的关键设计取舍。`ARCHITECTURE.md` 解释模块结构；本文更关注为什么这样做，以及这些选择带来的边界。

## Runtime 拥有执行权

LLM 只负责生成结构化 `Decision`，不直接执行工具。所有工具调用必须经过 Runtime 的 step loop，再由 `ApprovalGate` 处理 human-in-loop 拦截，最后由 `ApprovalGate` 调用 `ToolExecutor` 执行已放行的工具调用。

这个取舍让系统有一个明确的控制点：

- Runtime 可以限制最大 step 数，避免无限循环。
- Runtime 可以把每次工具调用记录成 `Step`。
- Runtime 可以在每个阶段发出结构化事件。
- LLM 输出即使符合 JSON schema，也仍然不能绕过 resolver 和 policy。

代价是 prompt 和 schema 需要更严格，模型输出不合法时会直接失败。当前项目接受这个代价，因为运行时治理比“尽量容错地执行模型意图”更重要。

## Tool 是受控能力，不是任意函数

`BaseTool` 统一处理参数校验、同步/异步适配、timeout、retry、`ToolException` 归一化和 `ToolResult` 包装。具体工具只实现自己的业务动作。

每个工具必须声明：

- 输入 schema
- 风险等级
- tag
- 副作用
- 是否 generic

这些元数据不是展示用的装饰信息，而是 policy、trace、CLI 和测试断言的输入。也因此，新增工具应该优先通过 `ToolProvider` 注册，而不是在 Runtime 里写特殊分支。

## Policy 独立于 Tool 实现

Tool 描述自己能做什么，Policy 决定当前调用是否允许。两者不互相嵌套。

当前 `PolicyEngine` 的重点是约束 `shell_exec`：

- 空命令直接拒绝。
- 能用专用工具表达的命令直接拒绝并给出建议。
- 有副作用或高风险的工具调用由 `ApprovalPolicy` 生成审批请求，`ApprovalBroker` 获取用户决策，`ApprovalGate` 根据 approve / reject / edit 决策决定是否执行工具。

这建立了一个重要边界：高风险 generic tool 不会因为模型生成了调用就自动运行。即使审批通过，`ShellExecTool` 也会使用 `shell=False`、限制 cwd 到 workspace、过滤环境变量、截断输出，并把非零退出码标记为失败。后续更完整的审批能力应该继续扩展 `ApprovalDecision`、Runtime event 和持久化状态，而不是绕过审批入口。

## Filesystem 默认限制在 Workspace 内

内置文件系统工具统一通过 `WorkspaceFileTool` 解析路径。相对路径基于 workspace，workspace 内绝对路径允许访问，任何逃逸 workspace 的路径都会被拒绝。

这个策略的目标不是提供完整沙箱，而是先阻断最容易出现的路径越权：

- `..` 逃逸
- 绝对路径探测
- `file_exists` 对 workspace 外路径做存在性检查

真正生产环境仍需要进程级沙箱、权限隔离和审计。本项目当前只把工具层边界做清楚。

## Event 是集成边界

Runtime 通过 `EventBus` 发出 `thought`、`tool_call`、`tool_execution`、`observation`、`final_result` 等事件。CLI、JSONL trace writer 和测试 probe 都应作为事件订阅者存在。

这样可以避免 Runtime 绑定某一种 UI 或日志实现：

- CLI 负责渲染，不负责调度。
- JSONL writer 负责持久化事件，不影响执行逻辑。
- 测试可以订阅事件断言顺序和内容。

新增可观测性能力时，优先订阅事件，而不是把日志逻辑塞进 Runtime 主循环。

## Trace 是事件回放材料，不是状态数据库

JSONL trace 文件记录 RuntimeEvent，用于理解一次运行中发生了什么。它适合做摘要、排障、回放展示和测试材料。

它不承担以下职责：

- 恢复正在运行的 AgentState
- 替代数据库
- 作为权限审批的唯一审计来源

如果后续要支持 resumable run 或长期状态，应单独引入 state persistence，而不是把 JSONL trace 扩展成隐式状态存储。

## LLM Provider 错误要归一化

`BaseLLM` 定义通用异常：

- `LLMConfigError`：本地配置缺失或非法。
- `LLMProviderError`：provider 调用或响应解析失败。

具体 provider 可以保留原始异常链，但向上层暴露稳定异常类型。这样 CLI、Runtime 和测试不需要依赖 OpenAI SDK 或某个供应商的异常细节。

Qwen provider 当前做了两件事：

- 启动时校验 `DASHSCOPE_API_KEY` 和 `QWEN_MODEL`。
- completion 请求失败时按配置重试，重试耗尽后抛 `LLMProviderError`。

## Public API 保守导出

根包 `codecraft` 导出程序化嵌入最常用的对象，例如 `AgentRuntime`、`Agent`、`ToolExecutor`、`EventBus`、`BaseLLM`、`QwenLLM`、`BaseTool` 和 `create_tool_registry`。

这不表示所有内部模块都是稳定 API。当前约定是：

- 根包和子包 `__all__` 中的名字是优先稳定的导入路径。
- 深层模块路径仍可在项目内部使用。
- 新增公共对象时应补 public API 测试。

## 当前仍未解决的问题

以下问题目前没有被隐藏，而是留作后续设计：

- 审批决策还没有持久化成可恢复状态。
- `shell_exec` 没有真正的进程级隔离。
- memory compression 仍是简单滚动摘要。
- 没有 resumable run。
- 没有多 provider 选择策略。
- 没有 OpenTelemetry 或结构化 metrics。

这些问题属于后续上线强化项，不应该通过在现有 Runtime 里增加隐式分支来解决。
