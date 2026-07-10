from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from codecraft.approval import ApprovalManager, ApprovalPolicy
from codecraft.core.ids import new_id
from codecraft.core.runtime import AgentRuntime
from codecraft.core.session_store import SessionStore
from codecraft.core.trace_report import build_trace_report, render_trace_json
from codecraft.eval.suite import (
    EVAL_SUITE_NAME,
    EvalTask,
    evaluate_task,
    seed_workspace,
)
from codecraft.llm import LLMProviderRegistry
from codecraft.sandbox import SandboxMode
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.input import SessionInput
from codecraft.schema.session import SessionConfig, SessionSource
from codecraft.tool import (
    ApplyPatchTool,
    ListFilesTool,
    ReadFileTool,
    ToolRegistry,
    WorkspaceSearchTool,
    WriteFileTool,
)

EVAL_REPORT_SCHEMA_VERSION = 1


async def run_eval_suite(
    *,
    tasks: Sequence[EvalTask],
    base_config: SessionConfig,
    llm_providers: LLMProviderRegistry,
    output_dir: Path,
    on_task_complete: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run fixed tasks sequentially and return a deterministic score report."""
    run_id = new_id("eval_")
    started_at = datetime.now(UTC)
    started = monotonic()
    output_dir = output_dir.expanduser().resolve()
    _ensure_new_run_directory(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "workspaces").mkdir(exist_ok=True)
    (output_dir / "traces").mkdir(exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        result = await _run_task(
            task=task,
            base_config=base_config,
            llm_providers=llm_providers,
            output_dir=output_dir,
            run_id=run_id,
        )
        results.append(result)
        if on_task_complete is not None:
            on_task_complete(index, len(tasks), result)

    finished_at = datetime.now(UTC)
    passed_count = sum(result["status"] == "passed" for result in results)
    task_count = len(results)
    return {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "suite": EVAL_SUITE_NAME,
            "model_provider": base_config.model_provider,
            "model": base_config.model,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": int((monotonic() - started) * 1000),
            "output_dir": str(output_dir),
        },
        "metrics": {
            "task_count": task_count,
            "passed_count": passed_count,
            "failed_count": task_count - passed_count,
            "success_rate": (passed_count / task_count * 100) if task_count else 0.0,
            "tool_call_count": sum(result["tool_call_count"] for result in results),
        },
        "results": results,
    }


async def _run_task(
    *,
    task: EvalTask,
    base_config: SessionConfig,
    llm_providers: LLMProviderRegistry,
    output_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    workspace = output_dir / "workspaces" / task.task_id
    seed_workspace(task, workspace)
    session_id = new_id("ses_eval_")
    config = base_config.model_copy(
        update={
            "session_id": session_id,
            "thread_id": new_id("thr_eval_"),
            "source": SessionSource.CLI_EVAL,
            "cwd": workspace,
            "workspace_roots": [workspace],
            "codecraft_home": output_dir / ".codecraft",
            "approval_policy": ApprovalPolicy.NEVER,
            "sandbox_mode": SandboxMode.WORKSPACE_WRITE,
            "network_access": False,
            "project_instructions": None,
            "user_instructions": None,
            "metadata": {
                **base_config.metadata,
                "eval_run_id": run_id,
                "eval_task_id": task.task_id,
            },
        }
    )
    runtime = AgentRuntime(
        session_store=SessionStore(config.codecraft_home),
        llm_providers=llm_providers,
        tool_registry=_eval_tool_registry(),
        approval_manager=ApprovalManager(policy=ApprovalPolicy.NEVER),
    )
    started = monotonic()
    events: list[RuntimeEvent] = []
    runtime_error: str | None = None

    try:
        thread = await runtime.create_thread(config)
        await thread.submit(SessionInput.user_message(new_id("inp_eval_"), task.prompt))
        while True:
            event = await thread.next_event()
            events.append(event)
            if event.type in {
                RuntimeEventType.TURN_FINISHED,
                RuntimeEventType.TURN_ABORTED,
            }:
                await thread.wait_until_idle()
                break
        events = (await thread.read_snapshot()).events
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"

    checks = evaluate_task(task, workspace)
    final_status = _final_status(events)
    passed = all(check["passed"] for check in checks) and final_status == "success"
    trace_report = build_trace_report(session_id, events)
    trace_path = output_dir / "traces" / f"{task.task_id}.trace.json"
    trace_path.write_text(render_trace_json(trace_report), encoding="utf-8")

    return {
        "task_id": task.task_id,
        "title": task.title,
        "category": task.category,
        "prompt": task.prompt,
        "status": "passed" if passed else "failed",
        "duration_ms": int((monotonic() - started) * 1000),
        "session_id": session_id,
        "final_status": final_status,
        "answer": _final_answer(events),
        "tool_call_count": sum(
            event.type == RuntimeEventType.TOOL_CALL_FINISHED for event in events
        ),
        "checks": checks,
        "workspace": str(workspace),
        "trace_json": str(trace_path.relative_to(output_dir)),
        "error": runtime_error,
    }


def _eval_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ReadFileTool(),
            ListFilesTool(),
            WorkspaceSearchTool(),
            WriteFileTool(),
            ApplyPatchTool(),
        ]
    )


def _ensure_new_run_directory(output_dir: Path) -> None:
    reserved = (
        output_dir / ".codecraft",
        output_dir / "workspaces",
        output_dir / "traces",
        output_dir / "eval-report.json",
        output_dir / "eval-report.html",
    )
    if any(path.exists() for path in reserved):
        raise FileExistsError(
            f"Evaluation output already contains run artifacts: {output_dir}"
        )


def _final_status(events: list[RuntimeEvent]) -> str:
    for event in reversed(events):
        if event.type == RuntimeEventType.TURN_FINISHED:
            return str(event.payload.get("status") or "success")
        if event.type == RuntimeEventType.TURN_ABORTED:
            return "aborted"
        if event.type == RuntimeEventType.ERROR:
            return "error"
    return "error"


def _final_answer(events: list[RuntimeEvent]) -> str:
    for event in reversed(events):
        if event.type == RuntimeEventType.TURN_FINISHED:
            return str(event.payload.get("answer") or "")
    return ""
