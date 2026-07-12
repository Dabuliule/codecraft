# CodeCraft

[中文文档](README.zh-CN.md)

CodeCraft is a local coding-agent runtime for working inside a repository. It is focused on the runtime pieces that make an agent governable: configuration, prompt/instruction loading, model providers, tool execution, approval, session event logs, resume, and inspection.

The project is currently being rebuilt toward a v1.0 runtime. It already runs real multi-turn CLI sessions with Qwen, DeepSeek, or OpenAI-compatible providers, but it is still an application-level sandbox, not an OS-level isolation system.

License: Apache-2.0.

## What It Does

- Runs coding tasks from the CLI with `exec`, `chat`, and `resume`.
- Loads configuration from user, profile, project, and explicit config files.
- Injects runtime instructions from built-in instructions plus `AGENTS.md` / `CODECRAFT.md`.
- Calls OpenAI-compatible providers, including Qwen, DeepSeek, and OpenAI.
- Exposes tools to the model through structured tool schemas, not by hardcoding tool descriptions into the prompt.
- Executes all tool calls through `ToolRunner`.
- Gates write, patch, bash, and risky commands through approval policy.
- Stores session events as JSONL under `~/.codecraft/sessions`.
- Reconstructs conversation history from session events for resume.
- Provides CLI inspection and trace export for events, tools, errors, raw logs, and invalid sessions.
- Runs a fixed 10-task coding-agent evaluation suite with deterministic grading and JSON/HTML reports.

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

No real-provider benchmark baseline has been recorded yet. Current automated
verification uses the mock provider and does not spend model API credits.

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
| `workspace_search` | Search workspace paths and text content | Returns paths, line numbers, and snippets |
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

Sandbox modes:

| Mode | Behavior |
| --- | --- |
| `read_only` | Allows read-only tools only |
| `workspace_write` | Allows workspace writes/process execution, still governed by approval and command policy |
| `danger_full_access` | Reserved for future expansion; still application-level, not OS isolation |

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
uv sync
uv run codecraft chat
```

Quality checks:

```zsh
uv run ruff check .
uv run pytest
```

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

Current test coverage includes runtime events, session store, resume, config loading, prompt injection, providers, tool runner, workspace tools, bash policy, approval flow, and CLI behavior.

## Current Limitations

- No OS-level sandbox.
- No automatic pruning of invalid sessions yet.
- No web/GitHub/cloud tools in v1.0 scope.
- `resume --last` resumes the latest valid session; targeted interactive resume by explicit session id is not implemented yet.
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
  sandbox/       command and sandbox policy
  schema/        runtime, session, input, and tool schemas
  tool/          tool abstraction, registry, runner, built-in tools
```
