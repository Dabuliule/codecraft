from __future__ import annotations

import json
from html import escape
from typing import Any


def render_eval_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def render_eval_html(report: dict[str, Any]) -> str:
    run = report["run"]
    metrics = report["metrics"]
    title = f"CodeCraft Eval {run['run_id']}"
    rows = "\n".join(_result_row(result) for result in report["results"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --bg: #f6f8fb; --panel: #fff; --ink: #152033;
      --muted: #657187; --line: #d8dfeb; --ok: #16734a; --bad: #b42318; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 24px 48px; }}
    h1 {{ margin: 0; font-size: 28px; }}
    .muted {{ color: var(--muted); }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px; margin: 20px 0 28px; }}
    .metric {{ padding: 14px; background: var(--panel); border: 1px solid var(--line);
      border-radius: 8px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel);
      border: 1px solid var(--line); }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left;
      vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); }}
    tr:last-child td {{ border-bottom: 0; }}
    .passed {{ color: var(--ok); font-weight: 700; }}
    .failed, .error {{ color: var(--bad); font-weight: 700; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    a {{ color: inherit; }}
  </style>
</head>
<body>
<main>
  <h1>{escape(title)}</h1>
  <p class="muted">{escape(run["suite"])} · {escape(run["model_provider"])}/{escape(run["model"])}</p>
  <section class="metrics">
    {_metric("Success Rate", f"{metrics['success_rate']:.1f}%")}
    {_metric("Passed", metrics["passed_count"])}
    {_metric("Failed", metrics["failed_count"])}
    {_metric("Tool Calls", metrics["tool_call_count"])}
    {_metric("Duration", f"{run['duration_ms']} ms")}
  </section>
  <table>
    <thead><tr><th>Task</th><th>Category</th><th>Status</th><th>Checks</th><th>Tools</th><th>Trace</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</main>
</body>
</html>
"""


def _metric(label: str, value: Any) -> str:
    return (
        f'<div class="metric"><strong>{escape(str(value))}</strong>'
        f'<span class="muted">{escape(label)}</span></div>'
    )


def _result_row(result: dict[str, Any]) -> str:
    failed_checks = [
        _check_label(check) for check in result["checks"] if not check["passed"]
    ]
    check_summary = "all passed" if not failed_checks else "; ".join(failed_checks)
    trace = result.get("trace_json")
    trace_link = (
        f'<a href="{escape(str(trace))}">JSON</a>'
        if trace
        else '<span class="muted">-</span>'
    )
    return (
        "<tr>"
        f"<td><code>{escape(result['task_id'])}</code><br>{escape(result['title'])}</td>"
        f"<td>{escape(result['category'])}</td>"
        f'<td class="{escape(result["status"])}">{escape(result["status"])}</td>'
        f"<td>{escape(check_summary)}</td>"
        f"<td>{escape(str(result['tool_call_count']))}</td>"
        f"<td>{trace_link}</td>"
        "</tr>"
    )


def _check_label(check: dict[str, Any]) -> str:
    suffix = f".{check['json_path']}" if check.get("json_path") else ""
    return f"{check['path']}{suffix} ({check['kind']})"
