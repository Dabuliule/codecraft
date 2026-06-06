# Design Notes

This document records current implementation choices and boundaries. For the full design, see `docs/design/codecraft-runtime-sdd.md`.

## Runtime Owns Execution

The model can request work, but it never receives direct execution authority. A tool call emitted by a provider must pass through:

```text
Turn -> ToolRunner -> SandboxPolicy -> ApprovalManager -> BaseTool
```

This gives the runtime one place to enforce:

- max turn steps;
- event emission;
- argument validation;
- workspace and sandbox rules;
- human approval;
- error normalization.

The tradeoff is that tool execution is more structured and less permissive than a free-form agent loop. That is intentional: CodeCraft prioritizes auditability and recovery over silently doing what the model appears to want.

## Events Are The Integration Boundary

`RuntimeEvent` is the boundary between core runtime, CLI rendering, session logs, and future UI surfaces.

Important rules:

- `Session.emit()` is the only event creation path during a session.
- Events are written to `SessionStore` before being published through `EventBus`.
- CLI consumes events; it does not inspect or mutate session internals.
- JSONL session logs are the source for inspect, resume, and debugging.

This is why assistant streaming, tool starts/finishes, approvals, errors, token counts, and final turn status are all represented as events.

## JSONL Is A Fact Log, Not A Hidden Database

The session log is intentionally simple JSONL:

```text
~/.codecraft/sessions/YYYY/MM/DD/<session_id>.jsonl
```

It is used for:

- audit;
- resume;
- diagnostics;
- invalid session inspection;
- tests.

It is not an OS-level lock manager, a transactional database, or a replacement for future long-term storage. If future versions need stronger persistence semantics, they should add that explicitly instead of hiding database behavior inside JSONL append.

## Resume Reconstructs Conversation, Not Effects

Resume rebuilds conversation history from events. It must not replay historical tool calls, because that would repeat side effects such as file writes, patches, or shell commands.

Current reconstruction handles:

- user messages;
- assistant messages;
- function/tool call messages;
- tool results;
- compaction summaries.

This design makes session logs useful without turning resume into a dangerous re-execution mechanism.

## Tool Metadata Drives Governance

Tools declare `effects` and `requires_approval`. These are not just documentation; `ToolRunner`, `SandboxPolicy`, `ApprovalManager`, provider tool schemas, and tests depend on them.

Current effect categories:

- `read_only`
- `workspace_write`
- `process_exec`
- `network`
- `external`

The practical rule is: add a new tool by giving it a Pydantic args schema, accurate effects, and a `ToolResult` contract. Do not add special execution branches in CLI or `Session`.

## Sandbox Is Application-Level

CodeCraft v1.0 does not provide OS-level isolation. The sandbox layer is an application-level policy check.

It currently enforces:

- workspace path guard for filesystem tools;
- bash cwd guard;
- `read_only` mode blocks side-effecting tools;
- network effects are denied when `network_access=false`;
- command policy denies or prompts for risky shell commands.

This blocks common accidental escapes and gives clear audit events, but it does not protect against all malicious local process behavior. Stronger isolation would need a separate process/container sandbox.

## Approval Is Independent From Tool Code

Tools describe capabilities; approval decides whether the current call may run. Keeping those separate matters because:

- tests can verify approval events without executing the tool;
- future UI reviewers can approve/reject through `AgentThread`;
- policy can change without editing individual tools;
- rejected calls still produce structured tool-finished events.

`ApprovalManager` is intentionally not a tool executor. It evaluates and requests approval; `ToolRunner` owns the execution sequence.

## Provider Compatibility Is A Transport Detail

`OpenAICompatibleProvider` is a shared adapter for OpenAI-shaped APIs and event conversion. It is not a claim that OpenAI is a formal industry standard.

Qwen extends the compatible provider because DashScope exposes an OpenAI-compatible chat API. Qwen still has its own provider class and uses Chat Completions streaming, while OpenAI can use Responses-style streaming.

Provider-specific differences should stay inside provider adapters. `Turn` only consumes normalized `ModelEvent` values.

## Config Is Resolved Before Runtime Construction

Config precedence is:

```text
CLI explicit options / --config
> project .codecraft/config.toml
> profile ~/.codecraft/profiles/<name>.toml
> user ~/.codecraft/config.toml
> built-in defaults
```

`SessionConfig` stores the resolved runtime values, including provider connection fields such as `model_api_key_env` and `model_base_url`. This makes resume use the same session configuration rather than re-reading a potentially changed project config.

API keys should be provided through environment variables named by `api_key_env`; plaintext keys in TOML are intentionally not recommended.

## Public API Is Conservative

The root `codecraft` package exports the objects most useful for tests and embedding, such as:

- runtime/session/thread types;
- event/session/tool schemas;
- providers;
- built-in tools;
- approval and workspace helpers.

Deep module paths can still change as v1.0 stabilizes. New public exports should have tests, especially when they are intended for external embedding.

## Known Follow-Up Work

These are intentional future items rather than hidden assumptions:

- automatic context compaction beyond current event/reconstruction support;
- explicit interactive resume by session id;
- automatic invalid session pruning or repair;
- OS-level sandboxing;
- Web/GitHub/cloud tools;
- OpenTelemetry or structured metrics;
- stronger smoke/e2e release checks.
