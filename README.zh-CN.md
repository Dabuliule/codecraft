# CodeCraft

[English](README.md)

CodeCraft 是一个运行在本地代码仓库里的 Coding Agent Runtime。它关注的不是“再包一层模型接口”，而是把 Agent 真正执行任务时需要的运行时能力拆清楚：配置加载、提示词/项目指令、模型 provider、工具执行、审批、session 事件日志、恢复会话和诊断。

项目目前正在按 v1.0 runtime 方向重构。当前已经可以通过 Qwen、DeepSeek 或 OpenAI-compatible provider 运行真实的多轮 CLI 会话。默认本地执行使用应用层 guard；可选 Docker backend 会为 bash 进程增加 OS 级隔离。

许可证：Apache-2.0。

## CodeCraft 能做什么

- 通过 CLI 执行单轮任务、多轮聊天和恢复会话。
- 从用户级、profile、项目级、显式配置文件和 CLI 参数加载配置。
- 注入内置 runtime instructions，并读取 workspace 内的 `AGENTS.md` / `CODECRAFT.md`。
- 调用 Qwen、DeepSeek 和 OpenAI 等 OpenAI-compatible provider。
- 通过结构化 tool schema 把工具暴露给模型，而不是把工具说明硬塞进 prompt。
- 所有工具调用都必须经过 `ToolRunner`。
- 对写文件、apply patch、bash 和高风险命令执行审批。
- bash 可通过可插拔的 local 或 Docker sandbox backend 执行。
- 把 session 事件以 JSONL 存到 `~/.codecraft/sessions`。
- 从事件日志重建 conversation，用于 resume。
- 支持 CLI 查看和导出事件、工具调用、错误、原始日志和损坏 session。
- 内置 10 个固定 Coding Agent 任务，支持确定性判分和 JSON/HTML 成功率报告。
- 可连接 stdio MCP server，并让发现到的工具继续经过 sandbox、审批和 trace 链路。
- 可向其他 MCP host 提供只读仓库搜索和项目上下文。

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

启动全屏终端界面：

```zsh
uv run codecraft tui
```

TUI 会同时显示对话、runtime 状态、Token 用量和工具活动。Assistant Markdown 在流式输出时原位更新，高风险工具调用会打开审批弹窗，当前 turn 结束前输入框保持锁定。它消费与 CLI 相同的 `RuntimeEvent`，没有实现第二套 Agent loop。

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

导出可读 trace 报告：

```zsh
uv run codecraft trace <session_id>
uv run codecraft trace <session_id> --format json
uv run codecraft trace <session_id> --output-dir ./traces
```

默认会同时写出 `<session_id>.trace.json` 和 `<session_id>.trace.html`。

运行内置 Coding Agent 评测：

```zsh
uv run codecraft eval --list
uv run codecraft eval
uv run codecraft eval --task locate-legacy-token
uv run codecraft eval --task locate-legacy-token --repeat 3
uv run codecraft eval --limit 3 --output-dir ./outputs/eval-run
```

任务覆盖文件创建、定点修改、多文件同步、仓库检索、结构化数据、重构、项目指令和受约束的数据清理。每次 attempt 都在单独生成的 workspace 中运行，并通过文件内容或 JSON 字段做确定性判分。报告包含每题成功率、p50/p95 时延、Token 用量、工具失败数和失败分类。输出目录会保留 `eval-report.json`、`eval-report.html`、各次 attempt 的 workspace 和 JSON trace。

评测任务只能读取、检索、写入和 patch 自己生成的 workspace，不提供 bash 工具，也不开网络。完整评测会产生真实模型 API 调用，可以先用 `--task` 或 `--limit` 做小规模 smoke run。

目前尚未记录真实 provider 的 benchmark baseline。现有自动化验证使用 mock provider，不会消耗模型 API 额度。

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
backend = "local"
network_access = false

[instructions]
user = "回答尽量简洁。"
```

API key 建议放在环境变量里：

```zsh
export DASHSCOPE_API_KEY="你的 key"
```

CodeCraft 推荐使用 `api_key_env`，不推荐把明文 API key 写进 TOML。如果不配置 `api_key_env`，CodeCraft 会按 provider 使用默认值：Qwen 使用 `DASHSCOPE_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`，OpenAI 使用 `OPENAI_API_KEY`。`base_url` 可选；Qwen 默认使用 DashScope compatible mode endpoint，DeepSeek 默认使用 `https://api.deepseek.com`。

常用 CLI 覆盖：

```zsh
uv run codecraft chat --provider qwen --model qwen-plus
uv run codecraft chat --provider deepseek --model deepseek-v4-flash
uv run codecraft chat --config ./my-config.toml
uv run codecraft chat --profile work
uv run codecraft chat --approval-policy on_request
uv run codecraft chat --network
```

## Provider

当前 provider：

- `qwen`
- `deepseek`
- `openai`

它们都基于 OpenAI-compatible provider。Qwen 和 DeepSeek 通过 Chat Completions 风格 adapter 实现，因为它们的兼容 API 提供 chat/function-style 调用形态。

内置默认模型配置：

```toml
[model]
provider = "qwen"
name = "qwen-plus"
# qwen 的 api_key_env 默认是 DASHSCOPE_API_KEY
# qwen 的 base_url 默认是 DashScope compatible mode
```

DeepSeek 示例：

```toml
[model]
provider = "deepseek"
name = "deepseek-v4-flash"
# deepseek 的 api_key_env 默认是 DEEPSEEK_API_KEY
# deepseek 的 base_url 默认是 https://api.deepseek.com
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
| `workspace_search` | 搜索 workspace 内路径和文本内容 | 返回路径、行号和片段 |
| `write_file` | 写入 workspace 内文本文件 | 需要审批 |
| `apply_patch` | 在 workspace 内应用 unified diff | 需要审批 |
| `bash` | 在 workspace 内运行 shell 命令 | command policy + 审批 + local/Docker backend |

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
| `danger_full_access` | 不再按 mode 限制 tool effect；网络策略、审批和 backend 隔离仍然生效 |

Sandbox mode 决定哪些能力可以执行，backend 决定审批通过的 bash 进程在哪里运行。默认 `local` backend 直接在宿主机执行，不提供 OS 级隔离。

### Docker Sandbox

先构建项目提供的镜像：

```zsh
docker build -f docker/sandbox.Dockerfile -t codecraft-sandbox:py311 docker
```

然后通过配置启用：

```toml
[sandbox]
mode = "workspace_write"
backend = "docker"
network_access = false

[sandbox.docker]
image = "codecraft-sandbox:py311"
cpus = 1.0
memory_mb = 1024
pids_limit = 256
tmpfs_mb = 256
env_allowlist = []
```

CodeCraft 使用 `--pull never` 启动容器，因此镜像必须预先存在于本机。项目需要其他语言或工具链时，可以配置自定义镜像。

Docker backend 为每条 bash 命令创建一个临时容器。容器根文件系统只读，`/tmp` 使用有容量限制的 tmpfs，并使用宿主机 UID/GID、移除 Linux capabilities、启用 `no-new-privileges`、限制 CPU/内存/PID、只挂载 workspace、仅转发显式允许的环境变量；关闭网络时还会使用 `--network none`。超时容器会被强制清理。

重要边界：Docker 隔离的是 bash 进程，不会让挂载的仓库免受主动写入。在 `workspace_write` 模式下，真实 workspace 会以可写方式挂载；内置文件工具仍在宿主机运行并受 `WorkspaceGuard` 约束。审批和 command policy 仍是安全模型的一部分。

## MCP 工具

CodeCraft 可以启动显式配置的 stdio MCP server，完成 MCP lifecycle 握手和工具发现，并以 `mcp__project_tools__lookup` 这样的命名空间暴露给模型。每个 server 在一次 runtime 生命周期内复用一个连接，并在 runtime 退出时关闭。

```toml
[mcp.servers.project_tools]
command = "python"
args = ["tools/mcp_server.py"]
timeout_seconds = 30
max_tools = 128
env_allowlist = ["PROJECT_API_TOKEN"]

[mcp.servers.project_tools.tools.calculate]
effects = ["read_only"]
requires_approval = false

[mcp.servers.project_tools.tools.lookup]
effects = ["network", "external"]
requires_approval = true
```

远端 JSON Schema 同时用于模型可见的 tool schema 和本地参数校验。文本和 structured result 会被保留；二进制内容只记录摘要，避免把 base64 写进 session log。工具名会经过命名空间、字符清理和长度限制，以兼容模型 provider。

MCP tool annotations 只作为诊断 metadata 保存，绝不直接用于授权。没有 per-tool 配置覆盖时，发现到的工具默认带 `network` 和 `external` effect，并要求审批；当 `network_access=false` 时，这些默认调用会被 `SandboxPolicy` 拒绝。

重要边界：显式配置 stdio server，等于授权 CodeCraft 在工具发现前启动这个宿主机进程。子进程只继承 MCP SDK 的少量安全默认环境变量和 `env_allowlist` 中的变量，但当前不会自动进入 Docker bash sandbox。Network effect 可以约束工具调用，不能从物理上移除一个已受信任宿主进程的网络能力。

### 对外提供仓库上下文

CodeCraft 也可以作为只读 stdio MCP server，供其他 Agent host 使用：

```zsh
codecraft mcp-server --workspace /仓库的绝对路径
```

它会暴露结构化 `search_repository` 工具和两个 resources：

```text
codecraft://workspace/metadata
codecraft://workspace/instructions
```

搜索工具复用 `ContextEngine`，有索引时使用 lexical/symbol retrieval，并保留确定性 scan fallback。搜索路径必须经过 `WorkspaceGuard`；这个 server 不暴露 write、patch、bash 或 Agent loop。

CodeCraft client 可以用下面的只读本地策略连接：

```toml
[mcp.servers.codecraft_repo]
command = "codecraft"
args = ["mcp-server", "--workspace", "/仓库的绝对路径"]

[mcp.servers.codecraft_repo.tools.search_repository]
effects = ["read_only"]
requires_approval = false
```

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

构建 sandbox 镜像后，可以显式运行 Docker 集成测试：

```zsh
CODECRAFT_RUN_DOCKER_TESTS=1 uv run pytest -m integration
```

普通测试会跳过这项集成测试；CI 会在独立 job 中构建镜像并真实运行。

Conventional Commits（提交信息不符合时会阻止 push）：

```zsh
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

提交格式：

```text
type(scope): subject
```

示例：

```text
feat(cli): add resume summary option
fix(tool): handle empty apply_patch payload
chore: update workflow permissions
```

当前测试覆盖 runtime events、session store、resume、配置加载、prompt 注入、模型 provider、MCP stdio client/server 互操作、tool runner、workspace 工具、bash policy、local/Docker sandbox backend、approval flow、CLI 行为和 Textual pilot 交互。

## 当前限制

- Docker 隔离依赖已经安装并运行的 Docker engine，以及预先构建的镜像。
- Docker 当前为每条命令创建临时容器，还没有 warm pool 或持久化工具缓存。
- Docker 只隔离 bash 执行；内置文件工具仍使用宿主机 workspace guard。
- MCP client 只消费 stdio tools；尚未消费 Streamable HTTP、resources、prompts 和动态 tool-list notification。
- CodeCraft MCP server 只暴露仓库搜索和两个只读 resources，不暴露通用 Agent 执行。
- 配置的 stdio MCP server 作为受信任宿主进程运行；尚未自动放进 Docker 隔离。
- TUI 当前只展示一个活动 session；session 浏览、resume 选择和 trace 面板属于后续工作。
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
  eval/          固定 Agent 任务、确定性判分、评测报告
  llm/           provider 接口和 OpenAI-compatible provider
  prompt/        内置指令、项目指令加载、prompt builder
  sandbox/       命令和沙箱策略
  schema/        runtime、session、input、tool schema
  tool/          tool 抽象、registry、runner、内置工具
```
