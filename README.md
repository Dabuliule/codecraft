# CodeCraft

[中文文档](README.zh-CN.md)

CodeCraft is a local coding-agent runtime for working inside a repository. It is focused on the runtime pieces that make an agent governable: configuration, prompt/instruction loading, model providers, tool execution, approval, session event logs, resume, and inspection.

The project is currently being rebuilt toward a v1.0 runtime. It already runs real multi-turn CLI sessions with Qwen, DeepSeek, or OpenAI-compatible providers. Local execution uses application-level guards by default; an optional Docker backend adds OS-level isolation for bash processes.

License: Apache-2.0.

## What It Does

- Runs coding tasks from the CLI with `exec`, `chat`, and `resume`.
- Loads configuration from user, profile, project, and explicit config files.
- Injects runtime instructions from built-in instructions plus `AGENTS.md` / `CODECRAFT.md`.
- Calls OpenAI-compatible providers, including Qwen, DeepSeek, and OpenAI.
- Exposes tools to the model through structured tool schemas, not by hardcoding tool descriptions into the prompt.
- Executes all tool calls through `ToolRunner`.
- Gates write, patch, bash, and risky commands through approval policy.
- Runs bash through a pluggable local or Docker sandbox backend.
- Stores session events as JSONL under `~/.codecraft/sessions`.
- Reconstructs conversation history from session events for resume.
- Provides CLI inspection and trace export for events, tools, errors, raw logs, and invalid sessions.
- Runs a fixed 10-task coding-agent evaluation suite with deterministic grading and JSON/HTML reports.
- Benchmarks repository retrieval with a fixed multi-language corpus, quality metrics, latency, and scan-cost reports.
- Connects stdio MCP servers and routes discovered tools through normal sandbox, approval, and trace handling.
- Serves read-only repository search and project context to other MCP hosts.

## Installation

CodeCraft is currently suitable for alpha/testing installs from GitHub.

Install with `uv`:

```zsh
uv tool install git+https://github.com/Dabuliule/codecraft.git
```

Update with `uv`:

```zsh
uv tool upgrade codecraft
```

Install with `pipx`:

```zsh
pipx install git+https://github.com/Dabuliule/codecraft.git
```

Update with `pipx`:

```zsh
pipx upgrade codecraft
```

After installation, run:

```zsh
codecraft chat
```

For local development from a clone:

```zsh
git clone https://github.com/Dabuliule/codecraft.git
cd codecraft
uv sync
uv run codecraft chat
```

## Current CLI

Run a single task:

```zsh
uv run codecraft exec "summarize this repository"
```

Start a multi-turn session:

```zsh
uv run codecraft chat
```

Start the full-screen terminal UI:

```zsh
uv run codecraft tui
```

The TUI keeps conversation, runtime status, token usage, and tool activity visible at the same time. Assistant Markdown updates in place while streaming, risky tool calls open an approval modal, and the input remains locked until the active turn finishes. It consumes the same `RuntimeEvent` stream as the CLI and does not implement a separate agent loop.

When the current repository has previous sessions, startup opens a session browser. Select one to restore its persisted configuration and conversation, or start a new session. Direct resume is also available:

```zsh
uv run codecraft tui --last
uv run codecraft tui --resume <session_id>
```

The restored visual history is bounded to keep long-running terminal sessions responsive; the runtime still reconstructs the full available model context from the event log.

Use the `Trace` command in the runtime panel to inspect the current persisted trace without leaving the TUI. The trace screen reuses the normal report model for aggregate metrics, a virtualized event table, and structured payload inspection.

Resume the latest valid session:

```zsh
uv run codecraft resume --last
```

Print only the latest valid session summary:

```zsh
uv run codecraft resume --last --summary
```

List valid sessions:

```zsh
uv run codecraft sessions
```

List valid and invalid sessions:

```zsh
uv run codecraft sessions --all
```

Inspect a session:

```zsh
uv run codecraft inspect <session_id>
uv run codecraft inspect <session_id> --events
uv run codecraft inspect <session_id> --tools
uv run codecraft inspect <session_id> --errors
uv run codecraft inspect <session_id> --raw
```

`inspect --raw` prints JSONL lines without validation, so it can diagnose a damaged session log.

Export a readable trace report:

```zsh
uv run codecraft trace <session_id>
uv run codecraft trace <session_id> --format json
uv run codecraft trace <session_id> --output-dir ./traces
```

By default, `trace` writes both `<session_id>.trace.json` and `<session_id>.trace.html`.

Run the built-in coding-agent evaluation suite:

```zsh
uv run codecraft eval --list
uv run codecraft eval
uv run codecraft eval --task locate-legacy-token
uv run codecraft eval --task locate-legacy-token --repeat 3
uv run codecraft eval --limit 3 --output-dir ./outputs/eval-run
```

The suite covers file creation, targeted and multi-file edits, repository search,
structured data, refactoring, project instructions, and constrained cleanup. Each
task attempt runs in its own generated workspace and is graded with deterministic
file or JSON checks. Reports include per-task success rates, p50/p95 duration,
token usage, tool failures, and failure categories. The output directory contains
`eval-report.json`, `eval-report.html`, the task workspaces, and one JSON trace per
attempt.

Evaluation tasks can read, search, write, and patch their generated workspaces.
They do not receive the bash tool or network access. A complete run makes real
model API calls, so use `--task` or `--limit` for a smaller smoke run.

A first real-provider baseline is recorded in
[`docs/EVAL_BASELINE.md`](docs/EVAL_BASELINE.md): Qwen3.7 Max Preview completed the
10-task suite once with 70.0% success, 200,485 total tokens, 13.4 s p50 latency,
and 22.6 s p95 latency. Exact graders exposed a trailing-newline defect in the
patch runtime; the document separates the original baseline from targeted
post-fix reruns. Automated CI still uses the mock provider and does not spend
model API credits.

Run the model-free repository retrieval baseline:

```zsh
uv run codecraft index .
uv run codecraft retrieval-eval --list
uv run codecraft retrieval-eval
uv run codecraft retrieval-eval --strategy auto
uv run codecraft retrieval-eval --strategy lexical
uv run codecraft retrieval-eval --repeat 10 --output-dir ./outputs/retrieval-run
```

`codecraft index` stores a workspace-keyed SQLite database under
`~/.codecraft/indexes/`. Re-running it is incremental: unchanged files are not
parsed again, changed files replace only their own chunks and symbols, and deleted
files are removed. Supported source files use Tree-sitter structure; other text
files use bounded line chunks. After an index exists, successful `write_file` and
`apply_patch` calls refresh only their changed files and record the refresh outcome
in tool metadata.

The fixed suite mixes exact symbols, paths, multi-file identifiers, scoped docs,
and natural-language intent over Python, TypeScript, Go, TOML, and Markdown. Its
JSON/HTML reports include Recall@1, Recall@5, Precision@5, MRR, p50/p95 latency,
scanned files and bytes, returned context size, and irrelevant/zero-result counts. The current scan backend
intentionally scores zero on semantic-only cases; that measured gap is the baseline
for comparing the `auto`, `scan`, `lexical`, and `symbol` strategies and a future
optional semantic retriever. Normal `workspace_search` calls default to `auto`,
which executes a deterministic sequential route and stops at the first non-empty
result.

## Configuration

CodeCraft uses TOML configuration. Precedence is highest to lowest:

```text
CLI explicit options / --config
> project .codecraft/config.toml
> profile ~/.codecraft/profiles/<name>.toml
> user ~/.codecraft/config.toml
> built-in defaults
```

Recommended user-level config:

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
user = "Answer concisely."
```

Then set the API key through the environment:

```zsh
export DASHSCOPE_API_KEY="your key"
```

CodeCraft intentionally uses `api_key_env` instead of recommending plaintext API keys in TOML. If `api_key_env` is omitted, CodeCraft uses provider defaults: `DASHSCOPE_API_KEY` for Qwen, `DEEPSEEK_API_KEY` for DeepSeek, and `OPENAI_API_KEY` for OpenAI. `base_url` is optional; Qwen defaults to DashScope's compatible-mode endpoint and DeepSeek defaults to `https://api.deepseek.com`.

Useful CLI overrides:

```zsh
uv run codecraft chat --provider qwen --model qwen-plus
uv run codecraft chat --provider deepseek --model deepseek-v4-flash
uv run codecraft chat --config ./my-config.toml
uv run codecraft chat --profile work
uv run codecraft chat --approval-policy on_request
uv run codecraft chat --network
```

## Providers

Current providers:

- `qwen`
- `deepseek`
- `openai`

They use an OpenAI-compatible provider base. Qwen and DeepSeek are implemented through Chat Completions-style adapters because their compatible APIs expose chat/function-style calls.

Default built-in model settings:

```toml
[model]
provider = "qwen"
name = "qwen-plus"
# api_key_env defaults to DASHSCOPE_API_KEY for qwen
# base_url defaults to DashScope compatible mode for qwen
```

DeepSeek example:

```toml
[model]
provider = "deepseek"
name = "deepseek-v4-flash"
# api_key_env defaults to DEEPSEEK_API_KEY for deepseek
# base_url defaults to https://api.deepseek.com
```

## Prompt And Instructions

Each model call receives a system message assembled from:

```text
base_instructions
project_instructions
user_instructions
turn_context
conversation
```

Project instructions are loaded from these files inside the workspace:

```text
AGENTS.md
CODECRAFT.md
```

CodeCraft searches upward from the current working directory within the workspace root. Nearby instruction files have higher priority.

Tool schemas are not embedded in the prompt. They are passed through the provider `tools` parameter as structured schemas.

## Built-In Tools

Current tools:

| Tool | Purpose | Notes |
| --- | --- | --- |
| `read_file` | Read a text file inside the workspace | Read-only |
| `list_files` | List files/directories inside the workspace | Skips common noisy folders |
| `workspace_search` | Search workspace paths and text content | Deterministic `auto` routing, or explicit `scan`, indexed `lexical`, and indexed `symbol` strategies |
| `write_file` | Write a text file inside the workspace | Requires approval |
| `apply_patch` | Apply a unified diff inside the workspace | Requires approval |
| `bash` | Run a shell command from inside the workspace | Command policy + approval + local/Docker backend |

All tools execute through `ToolRunner`. `ToolRegistry` only registers and looks up tools; it does not execute them.

## Approval And Safety

Approval policies:

| Policy | Behavior |
| --- | --- |
| `never` | Do not ask for approval |
| `on_request` | Ask for tools/commands that require approval |
| `untrusted` | Ask for side-effecting tools |

The CLI prints approval details, including bash commands:

```text
[tool] bash: python -c 'print(1)'
[approval] bash risk=prompt reason=unknown command requires approval
command: python -c 'print(1)'
Approve? [y/N]:
```

Command policy classifies obvious safe commands, prompt-required commands, denied commands, and network commands. `python --version` and `python -V` are safe; arbitrary Python commands require approval.

Sandbox modes:

| Mode | Behavior |
| --- | --- |
| `read_only` | Allows read-only tools only |
| `workspace_write` | Allows workspace writes/process execution, still governed by approval and command policy |
| `danger_full_access` | Adds no mode-based effect restrictions; network policy, approval, and backend isolation still apply |

Sandbox mode controls which capabilities may run. The configured backend controls where an approved bash process runs. The default `local` backend executes on the host and is not OS isolation.

### Docker Sandbox

Build the supplied image once:

```zsh
docker build -f docker/sandbox.Dockerfile -t codecraft-sandbox:py311 docker
```

Then opt in through configuration:

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

The image must already exist locally because CodeCraft runs Docker with `--pull never`. Use a custom image when a repository needs another language or toolchain.

The Docker backend creates an ephemeral container per bash command. It uses a read-only container root, a bounded `/tmp` tmpfs, the host UID/GID, dropped Linux capabilities, `no-new-privileges`, CPU/memory/PID limits, workspace-only bind mounts, explicit environment-variable forwarding, and `--network none` when network is disabled. Timed-out containers are force removed.

Important boundary: Docker isolates bash processes, not the mounted repository from intentional writes. In `workspace_write` mode the real workspace is mounted read-write, while built-in file tools continue to run on the host behind `WorkspaceGuard`. Approval and command policy remain part of the security model.

## MCP Tools

CodeCraft can start explicitly configured stdio MCP servers, complete the MCP lifecycle handshake, discover their tools, and expose them to the model with names such as `mcp__project_tools__lookup`. Each server keeps one connection for the runtime lifetime and is closed when the runtime exits.

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

Remote JSON Schema is used both for model-visible tool definitions and local argument validation. Text and structured results are preserved; binary content is summarized instead of writing base64 payloads into session logs. Tool names are namespaced, sanitized, and bounded for model-provider compatibility.

MCP tool annotations are recorded as diagnostic metadata but never trusted for authorization. Unless configuration provides a per-tool override, discovered tools default to `network` plus `external` effects and require approval. With `network_access=false`, those default calls are denied by `SandboxPolicy`.

Important boundary: configuring a stdio server explicitly trusts CodeCraft to start that host process before tool discovery. Its environment contains the MCP SDK's small safe default set plus names in `env_allowlist`, but the process is not placed inside the Docker bash sandbox. Network effects govern tool calls; they cannot physically remove networking from an already trusted host server process.

### Serve Repository Context

CodeCraft can also act as a read-only stdio MCP server for another agent host:

```zsh
codecraft mcp-server --workspace /absolute/path/to/repository
```

It exposes the structured `search_repository` tool plus these resources:

```text
codecraft://workspace/metadata
codecraft://workspace/instructions
```

The search tool reuses `ContextEngine`, indexed lexical/symbol retrieval when available, and deterministic scan fallback. Search paths pass through `WorkspaceGuard`; write, patch, bash, and agent-loop capabilities are not exposed by this server.

Connect it back to a CodeCraft client with a read-only local policy:

```toml
[mcp.servers.codecraft_repo]
command = "codecraft"
args = ["mcp-server", "--workspace", "/absolute/path/to/repository"]

[mcp.servers.codecraft_repo.tools.search_repository]
effects = ["read_only"]
requires_approval = false
```

## Sessions And Resume

Session events are stored as JSONL:

```text
~/.codecraft/sessions/YYYY/MM/DD/<session_id>.jsonl
```

The event log includes session, turn, user, assistant, model tool call, tool start/finish, approval, token, error, and finish events.

`resume --last` loads the latest valid session, reconstructs conversation from events, and continues without replaying historical tools.

If a session log is invalid, normal listing skips it. To see invalid logs:

```zsh
uv run codecraft sessions --all
```

To inspect a damaged log:

```zsh
uv run codecraft inspect <session_id> --raw
```

## Development

Install and run from the repository:

```zsh
uv sync
uv run codecraft chat
```

Quality checks:

```zsh
uv run ruff check .
uv run pytest
```

Run the opt-in Docker integration test after building the sandbox image:

```zsh
CODECRAFT_RUN_DOCKER_TESTS=1 uv run pytest -m integration
```

Normal test runs skip this integration test. CI builds the image and runs it in a dedicated job.

Conventional Commits (push is blocked if commit messages are invalid):

```zsh
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

Commit message format:

```text
type(scope): subject
```

Examples:

```text
feat(cli): add resume summary option
fix(tool): handle empty apply_patch payload
chore: update workflow permissions
```

Current test coverage includes runtime events, session store, resume, config loading, prompt injection, model providers, MCP stdio client/server interoperability, tool runner, workspace tools, bash policy, local/Docker sandbox backends, approval flow, CLI behavior, and Textual pilot interaction tests.

## Current Limitations

- Docker isolation requires an installed, running Docker engine and a prebuilt image.
- Docker containers are currently ephemeral per command; there is no warm pool or persistent tool cache.
- Docker isolates bash execution only; built-in file tools use host-side workspace guards.
- The MCP client supports stdio tools only; Streamable HTTP, resources, prompts, and dynamic tool-list notifications are not consumed yet.
- The CodeCraft MCP server exposes repository search and two read-only resources, not general agent execution.
- Configured stdio MCP servers run as trusted host processes; automatic Docker isolation for MCP servers is not implemented.
- The TUI runs one active session at a time.
- No automatic pruning of invalid sessions yet.
- No web/GitHub/cloud tools in v1.0 scope.
- Full automatic context compaction is v1.1 scope.

## Runtime Shape

High-level flow:

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

Core package layout:

```text
src/codecraft/
  approval/      approval policies and reviewers
  cli/           Typer CLI
  config/        TOML config models and loader
  core/          runtime, sessions, turns, event log reconstruction
  eval/          fixed agent tasks, deterministic grading, eval reports
  llm/           provider interfaces and OpenAI-compatible providers
  prompt/        base instructions, project instruction loading, prompt builder
  retrieval/     fixed retrieval corpus, benchmark runner, quality reports
  sandbox/       command and sandbox policy
  schema/        runtime, session, input, and tool schemas
  tool/          tool abstraction, registry, runner, built-in tools
```
