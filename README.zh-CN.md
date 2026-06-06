# CodeCraft

[English](README.md)

CodeCraft 是一个运行在本地代码仓库里的 Coding Agent Runtime。它关注的不是“再包一层模型接口”，而是把 Agent 真正执行任务时需要的运行时能力拆清楚：配置加载、提示词/项目指令、模型 provider、工具执行、审批、session 事件日志、恢复会话和诊断。

项目目前正在按 v1.0 runtime 方向重构。当前已经可以通过 Qwen 或 OpenAI-compatible provider 运行真实的多轮 CLI 会话，但安全边界仍然是应用层 workspace guard 和 command policy，不是 OS 级沙箱。

许可证：Apache-2.0。

## CodeCraft 能做什么

- 通过 CLI 执行单轮任务、多轮聊天和恢复会话。
- 从用户级、profile、项目级、显式配置文件和 CLI 参数加载配置。
- 注入内置 runtime instructions，并读取 workspace 内的 `AGENTS.md` / `CODECRAFT.md`。
- 调用 Qwen 和 OpenAI 等 OpenAI-compatible provider。
- 通过结构化 tool schema 把工具暴露给模型，而不是把工具说明硬塞进 prompt。
- 所有工具调用都必须经过 `ToolRunner`。
- 对写文件、apply patch、bash 和高风险命令执行审批。
- 把 session 事件以 JSONL 存到 `~/.codecraft/sessions`。
- 从事件日志重建 conversation，用于 resume。
- 支持 CLI 查看事件、工具调用、错误、原始日志和损坏 session。

## 安装

CodeCraft 目前适合作为 alpha / 试用版从 GitHub 安装。

使用 `uv` 安装：

```zsh
uv tool install git+https://github.com/Dabuliule/codecraft.git
```

使用 `uv` 更新：

```zsh
uv tool upgrade codecraft
```

使用 `pipx` 安装：

```zsh
pipx install git+https://github.com/Dabuliule/codecraft.git
```

使用 `pipx` 更新：

```zsh
pipx upgrade codecraft
```

安装后运行：

```zsh
codecraft chat
```

从源码本地开发：

```zsh
git clone https://github.com/Dabuliule/codecraft.git
cd codecraft
uv sync
uv run codecraft chat
```

## 当前 CLI

执行单轮任务：

```zsh
uv run codecraft exec "总结一下这个仓库"
```

启动多轮会话：

```zsh
uv run codecraft chat
```

恢复最近一个有效会话：

```zsh
uv run codecraft resume --last
```

只查看最近有效会话摘要：

```zsh
uv run codecraft resume --last --summary
```

列出有效 session：

```zsh
uv run codecraft sessions
```

列出有效和损坏 session：

```zsh
uv run codecraft sessions --all
```

检查 session：

```zsh
uv run codecraft inspect <session_id>
uv run codecraft inspect <session_id> --events
uv run codecraft inspect <session_id> --tools
uv run codecraft inspect <session_id> --errors
uv run codecraft inspect <session_id> --raw
```

`inspect --raw` 不做 JSONL 校验，适合排查已经损坏的 session log。

## 配置

CodeCraft 使用 TOML 配置。优先级从高到低：

```text
CLI 显式参数 / --config
> 项目级 .codecraft/config.toml
> profile ~/.codecraft/profiles/<name>.toml
> 用户级 ~/.codecraft/config.toml
> 内置默认值
```

推荐的用户级配置：

```toml
# ~/.codecraft/config.toml
[model]
provider = "qwen"
name = "qwen-plus"
api_key_env = "DASHSCOPE_API_KEY"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

[approval]
policy = "on_request"

[sandbox]
mode = "workspace_write"
network_access = false

[instructions]
user = "回答尽量简洁。"
```

API key 建议放在环境变量里：

```zsh
export DASHSCOPE_API_KEY="你的 key"
```

CodeCraft 推荐使用 `api_key_env`，不推荐把明文 API key 写进 TOML。如果不配置 `api_key_env`，CodeCraft 会按 provider 使用默认值：Qwen 使用 `DASHSCOPE_API_KEY`，OpenAI 使用 `OPENAI_API_KEY`。`base_url` 可选；Qwen 默认使用 DashScope compatible mode endpoint。

常用 CLI 覆盖：

```zsh
uv run codecraft chat --provider qwen --model qwen-plus
uv run codecraft chat --config ./my-config.toml
uv run codecraft chat --profile work
uv run codecraft chat --approval-policy on_request
uv run codecraft chat --network
```

## Provider

当前 provider：

- `qwen`
- `openai`

它们都基于 OpenAI-compatible provider。Qwen 这样实现，是因为 DashScope 提供了 OpenAI-compatible API 形态，适合复用同一套 function/tool call 转换逻辑。

内置默认模型配置：

```toml
[model]
provider = "qwen"
name = "qwen-plus"
# qwen 的 api_key_env 默认是 DASHSCOPE_API_KEY
# qwen 的 base_url 默认是 DashScope compatible mode
```

## Prompt 和 Instructions

每次调用模型前，CodeCraft 会组装一条 system message，来源包括：

```text
base_instructions
project_instructions
user_instructions
turn_context
conversation
```

项目指令来自 workspace 内的：

```text
AGENTS.md
CODECRAFT.md
```

CodeCraft 会从当前工作目录开始向上查找，但不会越过 workspace root。离当前目录越近的指令文件优先级越高。

工具 schema 不写进 prompt，而是通过 provider 的 `tools` 参数以结构化 schema 传给模型。

## 内置工具

| 工具 | 作用 | 说明 |
| --- | --- | --- |
| `read_file` | 读取 workspace 内文本文件 | 只读 |
| `list_files` | 列出 workspace 内文件/目录 | 跳过常见噪声目录 |
| `write_file` | 写入 workspace 内文本文件 | 需要审批 |
| `apply_patch` | 在 workspace 内应用 unified diff | 需要审批 |
| `bash` | 在 workspace 内运行 shell 命令 | command policy + 审批 |

所有工具都通过 `ToolRunner` 执行。`ToolRegistry` 只负责注册和查找工具，不执行工具。

## 审批和安全边界

审批策略：

| 策略 | 行为 |
| --- | --- |
| `never` | 不询问审批 |
| `on_request` | 对声明需要审批的工具/命令询问 |
| `untrusted` | 对有副作用的工具询问 |

CLI 会展示审批细节，尤其是 bash 命令：

```text
[tool] bash: python -c 'print(1)'
[approval] bash risk=prompt reason=unknown command requires approval
command: python -c 'print(1)'
Approve? [y/N]:
```

Command policy 会区分安全命令、需要审批的命令、拒绝命令和网络命令。`python --version` 和 `python -V` 是安全命令；任意 Python 代码执行需要审批。

Sandbox mode：

| 模式 | 行为 |
| --- | --- |
| `read_only` | 只允许只读工具 |
| `workspace_write` | 允许 workspace 写入和进程执行，但仍受审批和 command policy 约束 |
| `danger_full_access` | 预留给未来扩展；仍然是应用层边界，不是 OS 级隔离 |

重要边界：CodeCraft v1.0 是应用层 workspace guard 和命令策略，不声明提供 OS 级沙箱。

## Session 和 Resume

Session 事件以 JSONL 存储：

```text
~/.codecraft/sessions/YYYY/MM/DD/<session_id>.jsonl
```

事件日志包含 session、turn、user、assistant、model tool call、tool start/finish、approval、token、error、finish 等事件。

`resume --last` 会加载最近一个有效 session，从事件重建 conversation，然后继续对话，不会重新执行历史工具。

如果 session log 损坏，默认列表会跳过它。要查看损坏日志：

```zsh
uv run codecraft sessions --all
```

要排查损坏日志：

```zsh
uv run codecraft inspect <session_id> --raw
```

## 开发

从仓库内安装和运行：

```zsh
uv sync
uv run codecraft chat
```

质量检查：

```zsh
uv run ruff check .
uv run pytest
```

当前测试覆盖 runtime events、session store、resume、配置加载、prompt 注入、provider、tool runner、workspace 工具、bash policy、approval flow 和 CLI 行为。

## 当前限制

- 没有 OS 级沙箱。
- 还没有自动清理 invalid session。
- v1.0 暂不做 Web/GitHub/cloud 工具。
- `resume --last` 只能恢复最近有效 session；还没有按指定 session id 进入交互式 resume。
- 完整自动 context compact 属于 v1.1 范围。

## Runtime 结构

高层流程：

```text
CLI
  -> ConfigLoader
  -> AgentRuntime
  -> AgentThread / Session / Turn
  -> LLMProvider
  -> ToolRunner
  -> ApprovalManager
  -> SessionStore JSONL events
```

核心目录：

```text
src/codecraft/
  approval/      审批策略和 reviewer
  cli/           Typer CLI
  config/        TOML 配置模型和加载器
  core/          runtime、session、turn、事件重建
  llm/           provider 接口和 OpenAI-compatible provider
  prompt/        内置指令、项目指令加载、prompt builder
  sandbox/       命令和沙箱策略
  schema/        runtime、session、input、tool schema
  tool/          tool 抽象、registry、runner、内置工具
```
