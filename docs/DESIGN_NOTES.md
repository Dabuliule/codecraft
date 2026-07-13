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

## Sandbox Is Layered

CodeCraft separates capability governance from process isolation. A bash call passes through:

```text
SandboxPolicy -> ApprovalManager -> CommandPolicy -> SandboxBackend
```

The policy layers enforce:

- workspace path guard for filesystem tools;
- bash cwd guard;
- `read_only` mode blocks side-effecting tools;
- network effects are denied when `network_access=false`;
- command policy denies or prompts for risky shell commands.

The default local backend executes approved commands on the host and therefore remains an application-level boundary. The optional Docker backend creates an ephemeral, resource-limited container with a read-only root, bounded tmpfs, dropped capabilities, `no-new-privileges`, explicit environment forwarding, workspace-only mounts, and optional network removal.

This boundary is intentionally precise: Docker isolates bash processes, while a workspace mounted read-write can still be changed by those processes. Built-in file tools remain host-side behind `WorkspaceGuard`. Approval and command policy are still required because process isolation is not intent validation.

## MCP Extends The Tool System

MCP tools are adapters, not a second execution path. A discovered remote tool becomes a `BaseTool` and therefore passes through the same `ToolRunner`, sandbox, approval, event, and trace pipeline as a built-in tool.

`ToolRegistry` owns async provider lifecycle because discovery must finish before the first model request. Startup is transactional: a failed provider closes previously started providers and exposes no partial dynamic tool set. Stdio connections persist for the runtime lifetime to avoid per-call process startup.

Remote annotations are intentionally not authorization. The MCP specification defines them as untrusted hints, so local configuration owns effects and approval requirements. Conservative defaults mark tools as networked and external; explicit per-tool configuration is required to treat a tool as read-only.

Configuring a stdio server authorizes its process to start on the host. Environment inheritance is restricted, but process-level Docker isolation is separate future work. This avoids claiming that call-time effect checks can constrain code already running inside a configured server.

CodeCraft's own MCP server is deliberately narrower than its client. It exports read-only repository context, not built-in write/process tools or the agent loop. This makes the server useful for interoperability without creating a second, approval-free path to CodeCraft side effects. Repository search remains a shared `ContextEngine` capability rather than a duplicate MCP-specific implementation.

## TUI Is An Event Projection

The Textual interface is another consumer of `RuntimeEvent`, not a parallel runtime. It submits normal `SessionInput` values and waits for approval through `AgentThread`, preserving session logs, policy decisions, and trace behavior across CLI and TUI surfaces.

Streaming UI state is local and disposable: assistant deltas update the current visual message block, while the persisted assistant event remains the recovery source. This keeps rendering concerns out of `Session` and lets headless pilot tests verify interaction without changing core execution semantics.

Session selection also stays above the runtime boundary. The TUI lists summaries through `AgentRuntime`, then rebuilds a selected session from its persisted `SessionConfig`; it does not merge current command-line configuration into old state. Restored UI history is bounded independently from conversation reconstruction, so rendering cost does not redefine model context.

Trace inspection is a snapshot over persisted events, not a second telemetry model. The TUI consumes `build_trace_report()` just like JSON/HTML export, while a virtualized table keeps inspection cost proportional to visible rows. The live event consumer continues behind the modal; reopening Trace obtains a fresh snapshot.

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
- warm Docker sandboxes and persistent tool caches;
- Streamable HTTP MCP transport, resources, prompts, and dynamic tool refresh;
- automatic Docker isolation for stdio MCP servers;
- Web/GitHub/cloud tools;
- OpenTelemetry or structured metrics;
- stronger smoke/e2e release checks.
