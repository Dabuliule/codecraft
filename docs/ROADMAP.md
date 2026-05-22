# Roadmap

本文档记录 `agent-runtime` 的近期演进计划。目标不是堆功能，而是把项目打磨成一个边界清楚、可运行、可测试、方便继续扩展的 Agent Runtime。

## 总体目标

近期迭代后，项目应该满足：

- README 能让新读者快速理解项目价值。
- 本地 demo 可以稳定跑通。
- 核心 Runtime 有端到端测试。
- Tool 执行有清晰安全边界。
- Policy 层能体现治理能力，而不是只有简单 if 判断。
- 执行轨迹可以被保存、查看和回放。
- 能清楚说明和 LangChain/function calling 的差异。

## Phase 1: 文档与测试地基

目标：先把项目讲清楚，并补上最关键的测试。

任务：

- [x] 重写 README，突出项目定位、架构、使用方式和 roadmap。
- [x] 增加架构设计文档。
- [x] 增加后续迭代 roadmap。
- [x] 增加测试用 scripted LLM。
- [x] 增加 Runtime 端到端测试：`read_file -> final_answer`。
- [x] 增加 PolicyEngine 测试：专用工具替代、空命令、高风险 shell。
- [x] 增加 BaseTool 测试：参数校验、timeout、retry、ToolException。

验收标准：

- `uv run pytest` 通过。
- `uv run ruff check .` 通过。
- 不依赖真实 LLM 也能测试 Runtime 主流程。

## Phase 2: 安全边界与审批模型

目标：让“可治理 Tool 执行系统”更有说服力。

任务：

- [x] 增加 workspace root 配置。
- [x] 文件系统工具统一做路径解析和越权检查。
- [x] 禁止通过 `..` 或绝对路径逃逸 workspace。
- [x] 区分只读工具、写入工具、删除工具。
- [x] 设计 `PolicyDecision` 的 allow / deny / require_approval 状态。
- [x] CLI 中展示需要审批的工具调用。
- [x] 为 policy 结果增加结构化 data，方便 trace 和测试断言。

验收标准：

- 文件工具只能操作允许的 workspace。
- 高风险操作不会静默执行。
- Policy 行为有单元测试覆盖。

## Phase 3: Trace、可观测性与 Demo

目标：让项目可以稳定展示，并让执行过程更像一个 runtime。

任务：

- [x] 增加 JSONL trace writer，订阅 RuntimeEvent。
- [x] 每次 run 生成 trace id 对应的 trace 文件。
- [x] 增加 trace replay 或 trace summary 命令。
- [x] CLI 增加 `/trace` 查看当前 trace 摘要。
- [ ] 准备一个稳定 demo：让 agent 分析当前项目并输出结构总结。
- [ ] README 增加 demo 命令和示例输出。

验收标准：

- 一次运行结束后可以在本地看到完整事件轨迹。
- 不打开代码也能通过 trace 理解 Agent 做了什么。
- demo 可以重复运行。

## Phase 4: 工程 polish 与项目说明

目标：把项目从“能跑”打磨到“好讲”。

任务：

- [x] 增加模型配置校验和友好错误提示。
- [ ] 增加 LLM provider 错误处理和重试策略。
- [ ] 梳理 public API，减少内部模块泄漏。
- [ ] 增加 `docs/DESIGN_NOTES.md`，整理关键设计取舍。
- [ ] 增加架构图或流程图。
- [ ] README 增加“设计取舍”和“未来扩展”章节。
- [ ] 检查中文/英文术语统一。

验收标准：

- 文档能清楚解释核心架构。
- 关键设计取舍有对应说明。
- policy、runtime、tool、event、state 的职责边界保持清晰。

## 可选增强

如果进度顺利，可以继续做：

- 多 provider LLM 支持。
- Tool 并行执行。
- 多 Agent 协作。
- Web UI trace viewer。
- OpenTelemetry metrics。
- SQLite 持久化 state。
- 更完整的 approval UI。

## 待讨论问题

这些问题适合后续在文档、issue 或设计记录中继续展开：

- 为什么不直接用 LangChain？
- 如何防止 Agent 乱执行 shell？
- Tool 执行失败后如何恢复？
- 多步任务如何避免上下文无限增长？
- 如何测试依赖 LLM 的系统？
- 如果支持生产环境，还缺哪些安全措施？
