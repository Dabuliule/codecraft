# CodeCraft

[中文文档](README.zh-CN.md)

CodeCraft is a local coding-agent runtime for working inside a repository. It is focused on the runtime pieces that make an agent governable: configuration, prompt/instruction loading, model providers, tool execution, approval, session event logs, resume, and inspection.

The project is currently being rebuilt toward a v1.0 runtime. It already runs real multi-turn CLI sessions with Qwen or OpenAI-compatible providers, but it is still an application-level sandbox, not an OS-level isolation system.

## What It Does

- Runs coding tasks from the CLI with `exec`, `chat`, and `resume`.
- Loads configuration from user, profile, project, and explicit config files.
- Injects runtime instructions from built-in instructions plus `AGENTS.md` / `CODECRAFT.md`.
- Calls OpenAI-compatible providers, including Qwen and OpenAI.
- Exposes tools to the model through structured tool schemas, not by hardcoding tool descriptions into the prompt.
- Executes all tool calls through `ToolRunner`.
- Gates write, patch, bash, and risky commands through approval policy.
- Stores session events as JSONL under `~/.codecraft/sessions`.
- Reconstructs conversation history from session events for resume.
- Provides CLI inspection for events, tools, errors, raw logs, and invalid sessions.

## Current CLI

Run a single task:

```zsh
uv run codecraft exec "summarize this repository"
```

Start a multi-turn session:

```zsh
uv run codecraft chat
```

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

[approval]
policy = "on_request"

[sandbox]
mode = "workspace_write"
network_access = false

[instructions]
user = "Answer concisely."
```

Then set the API key through the environment:

```zsh
export DASHSCOPE_API_KEY="your key"
```

CodeCraft intentionally uses `api_key_env` instead of recommending plaintext API keys in TOML.

Useful CLI overrides:

```zsh
uv run codecraft chat --provider qwen --model qwen-plus
uv run codecraft chat --config ./my-config.toml
uv run codecraft chat --profile work
uv run codecraft chat --approval-policy on_request
uv run codecraft chat --network
```

## Providers

Current providers:

- `qwen`
- `openai`

Both use an OpenAI-compatible provider base. Qwen is implemented as an OpenAI-compatible provider because DashScope exposes an OpenAI-compatible API surface for chat/function-style calls.

Default built-in model settings:

```toml
[model]
provider = "qwen"
name = "qwen-plus"
api_key_env = "DASHSCOPE_API_KEY"
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
| `write_file` | Write a text file inside the workspace | Requires approval |
| `apply_patch` | Apply a unified diff inside the workspace | Requires approval |
| `bash` | Run a shell command from inside the workspace | Command policy + approval |

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

Important boundary: CodeCraft v1.0 uses application-level workspace guards and command policy. It does not claim OS-level sandboxing.

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
uv pip install -e .
uv run codecraft chat
```

Quality checks:

```zsh
uv run ruff check .
uv run pytest
```

Current test coverage includes runtime events, session store, resume, config loading, prompt injection, providers, tool runner, workspace tools, bash policy, approval flow, and CLI behavior.

## Current Limitations

- No OS-level sandbox.
- No automatic pruning of invalid sessions yet.
- OpenAI and Qwen providers stream assistant text through runtime delta events.
- No web/GitHub/cloud tools in v1.0 scope.
- `resume --last` resumes the latest valid session; targeted interactive resume by explicit session id is not implemented yet.

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
  llm/           provider interfaces and OpenAI-compatible providers
  prompt/        base instructions, project instruction loading, prompt builder
  sandbox/       command and sandbox policy
  schema/        runtime, session, input, and tool schemas
  tool/          tool abstraction, registry, runner, built-in tools
```
