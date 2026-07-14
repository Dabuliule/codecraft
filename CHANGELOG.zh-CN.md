# 更新日志

[English](CHANGELOG.md)

CodeCraft 面向用户的重要变更都会记录在这里。本文档格式基于
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，包版本遵循
[PEP 440](https://peps.python.org/pep-0440/)。

## [未发布]

## [0.1.0a3] - 2026-07-13

### 新增

- 基于 Textual 的全屏界面，支持多轮会话、审批弹窗、会话浏览与恢复，
  以及 trace 查看。
- 增量仓库索引、确定性检索路由、仓库搜索工具和检索基准报告。
- 固定 Coding Agent 评测集，支持重复运行、确定性评分、指标统计，
  以及 JSON/HTML 报告。
- MCP client 和只读仓库上下文 MCP server。
- macOS/Linux 原生进程隔离，以及可选的 Docker 沙箱。
- 上下文压缩、受限的只读工具并发、分层运行时超时、结构化输出限制，
  以及各阶段工具耗时。

### 变更

- 裸 `codecraft` 命令现在启动全屏 TUI，替代原有的行式交互界面。
- TUI 成为唯一的多轮交互界面；具名 CLI 命令继续用于一次性任务、诊断、
  评测、索引和服务。
- 模型事件、session 输入、工具参数、审批、沙箱决策和工具结果采用更严格的
  运行时契约。
- Alpha 阶段将 CodeCraft 作为独立应用设计，而不是以兼容性为中心的 Python SDK。

### 修复

- 应用 patch 时保留文件末尾换行语义。
- 收紧命令分类、session 取消、模型流结束、工具批次顺序、错误报告和密钥脱敏。

### 兼容性

- 当前仍是 Alpha 版本，不保证与更早 Alpha 版本的 session 和配置 schema 兼容。

安装方式、验证证据和已知限制见
[v0.1.0a3 发布说明](docs/releases/v0.1.0a3.zh-CN.md)。

## [0.1.0a2] - 2026-06-11

### 新增

- 初始 GitHub Release workflow、CI matrix、Conventional Commit 校验和密钥扫描。

### 修复

- 在交互式 CLI 中正确渲染 assistant Markdown。

[未发布]: https://github.com/Dabuliule/codecraft/compare/v0.1.0a3...HEAD
[0.1.0a3]: https://github.com/Dabuliule/codecraft/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/Dabuliule/codecraft/releases/tag/v0.1.0a2
