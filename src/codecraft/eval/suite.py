from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

EVAL_SUITE_NAME = "codecraft-core-v1"


class EvalCheckType(StrEnum):
    FILE_EQUALS = "file_equals"
    FILE_CONTAINS = "file_contains"
    FILE_NOT_CONTAINS = "file_not_contains"
    JSON_EQUALS = "json_equals"


@dataclass(frozen=True)
class EvalCheck:
    kind: EvalCheckType
    path: str
    expected: Any
    json_path: str | None = None


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    title: str
    category: str
    prompt: str
    seed_files: dict[str, str]
    checks: tuple[EvalCheck, ...]


def get_eval_tasks() -> tuple[EvalTask, ...]:
    """Return the stable built-in coding-agent evaluation suite."""
    return (
        EvalTask(
            task_id="create-welcome-file",
            title="Create an exact file",
            category="file_creation",
            prompt=(
                "Create a file named welcome.txt containing exactly "
                "`hello, codecraft` followed by a newline. Do not change other files."
            ),
            seed_files={"README.md": "# Tiny workspace\n"},
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "welcome.txt",
                    "hello, codecraft\n",
                ),
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "README.md",
                    "# Tiny workspace\n",
                ),
            ),
        ),
        EvalTask(
            task_id="fix-calculator-bug",
            title="Make a minimal bug fix",
            category="targeted_edit",
            prompt=(
                "Fix the bug in calculator.py so add(2, 3) returns 5. Preserve the "
                "subtract function and the module comment exactly."
            ),
            seed_files={
                "calculator.py": (
                    "# Arithmetic helpers used by the invoice service.\n\n"
                    "def add(left, right):\n"
                    "    return left - right\n\n\n"
                    "def subtract(left, right):\n"
                    "    return left - right\n"
                )
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "calculator.py",
                    "# Arithmetic helpers used by the invoice service.\n\n"
                    "def add(left, right):\n"
                    "    return left + right\n\n\n"
                    "def subtract(left, right):\n"
                    "    return left - right\n",
                ),
            ),
        ),
        EvalTask(
            task_id="sync-package-version",
            title="Synchronize a multi-file change",
            category="multi_file_edit",
            prompt=(
                "Update the package version from 1.4.2 to 1.5.0 everywhere it is "
                "declared. Keep all unrelated text unchanged."
            ),
            seed_files={
                "pyproject.toml": ('[project]\nname = "tiny-app"\nversion = "1.4.2"\n'),
                "src/tiny_app/__init__.py": '__version__ = "1.4.2"\n',
                "README.md": "Tiny App supports protocol 1.4.2.\n",
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "pyproject.toml",
                    '[project]\nname = "tiny-app"\nversion = "1.5.0"\n',
                ),
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "src/tiny_app/__init__.py",
                    '__version__ = "1.5.0"\n',
                ),
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "README.md",
                    "Tiny App supports protocol 1.4.2.\n",
                ),
            ),
        ),
        EvalTask(
            task_id="write-quickstart",
            title="Create a nested documentation file",
            category="documentation",
            prompt=(
                "Create docs/quickstart.md. It must have the heading `# Quickstart` "
                "and mention both commands `uv sync` and `uv run tiny-app`."
            ),
            seed_files={"docs/.keep": "", "README.md": "# Tiny App\n"},
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "docs/quickstart.md",
                    "# Quickstart",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "docs/quickstart.md",
                    "uv sync",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "docs/quickstart.md",
                    "uv run tiny-app",
                ),
            ),
        ),
        EvalTask(
            task_id="update-json-settings",
            title="Edit structured configuration",
            category="structured_data",
            prompt=(
                "In settings.json, enable features.search and change retries to 3. "
                "Preserve the service name and keep the file valid JSON."
            ),
            seed_files={
                "settings.json": (
                    "{\n"
                    '  "service": "catalog",\n'
                    '  "features": {"search": false, "export": true},\n'
                    '  "retries": 2\n'
                    "}\n"
                )
            },
            checks=(
                EvalCheck(
                    EvalCheckType.JSON_EQUALS,
                    "settings.json",
                    True,
                    "features.search",
                ),
                EvalCheck(
                    EvalCheckType.JSON_EQUALS,
                    "settings.json",
                    3,
                    "retries",
                ),
                EvalCheck(
                    EvalCheckType.JSON_EQUALS,
                    "settings.json",
                    "catalog",
                    "service",
                ),
                EvalCheck(
                    EvalCheckType.JSON_EQUALS,
                    "settings.json",
                    True,
                    "features.export",
                ),
            ),
        ),
        EvalTask(
            task_id="locate-legacy-token",
            title="Retrieve repository context",
            category="repository_search",
            prompt=(
                "Find the file containing the exact text LEGACY_TOKEN. Create "
                "migration.txt containing only that file's relative path and a newline."
            ),
            seed_files={
                "src/current/auth.py": 'TOKEN_KIND = "CURRENT"\n',
                "src/legacy/auth.py": 'TOKEN_KIND = "LEGACY_TOKEN"\n',
                "docs/auth.md": "Authentication notes.\n",
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "migration.txt",
                    "src/legacy/auth.py\n",
                ),
            ),
        ),
        EvalTask(
            task_id="edit-production-timeout",
            title="Change the correct configuration section",
            category="contextual_edit",
            prompt=(
                "Change only the production timeout in config.ini from 20 to 45. "
                "Leave the development timeout and all comments unchanged."
            ),
            seed_files={
                "config.ini": (
                    "# Request settings\n"
                    "[development]\n"
                    "timeout = 20\n\n"
                    "[production]\n"
                    "timeout = 20\n"
                )
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "config.ini",
                    "# Request settings\n"
                    "[development]\n"
                    "timeout = 20\n\n"
                    "[production]\n"
                    "timeout = 45\n",
                ),
            ),
        ),
        EvalTask(
            task_id="deduplicate-timeout-constant",
            title="Refactor a shared constant",
            category="refactoring",
            prompt=(
                "Define DEFAULT_TIMEOUT = 30 in constants.py. Update api.py and "
                "worker.py to import and use DEFAULT_TIMEOUT instead of duplicating 30."
            ),
            seed_files={
                "constants.py": 'APP_NAME = "tiny-app"\n',
                "api.py": "timeout = 30\n",
                "worker.py": "timeout = 30\n",
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "constants.py",
                    "DEFAULT_TIMEOUT = 30",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "api.py",
                    "from constants import DEFAULT_TIMEOUT",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "api.py",
                    "timeout = DEFAULT_TIMEOUT",
                ),
                EvalCheck(
                    EvalCheckType.FILE_NOT_CONTAINS,
                    "api.py",
                    "timeout = 30",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "worker.py",
                    "from constants import DEFAULT_TIMEOUT",
                ),
                EvalCheck(
                    EvalCheckType.FILE_CONTAINS,
                    "worker.py",
                    "timeout = DEFAULT_TIMEOUT",
                ),
                EvalCheck(
                    EvalCheckType.FILE_NOT_CONTAINS,
                    "worker.py",
                    "timeout = 30",
                ),
            ),
        ),
        EvalTask(
            task_id="follow-project-instructions",
            title="Respect project instructions",
            category="instruction_following",
            prompt=("Mark the project ready according to the repository instructions."),
            seed_files={
                "AGENTS.md": (
                    "Do not modify locked.txt. To mark the project ready, append "
                    "the line `status=ready` to state.txt. Preserve existing lines.\n"
                ),
                "locked.txt": "owner=platform\n",
                "state.txt": "name=tiny-app\n",
            },
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "state.txt",
                    "name=tiny-app\nstatus=ready\n",
                ),
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "locked.txt",
                    "owner=platform\n",
                ),
            ),
        ),
        EvalTask(
            task_id="normalize-name-list",
            title="Apply constrained text transformation",
            category="data_cleanup",
            prompt=(
                "In names.txt, keep the first comment line unchanged, then sort the "
                "names alphabetically and remove duplicates."
            ),
            seed_files={"names.txt": "# Active users\nzoe\nalice\nbob\nalice\n"},
            checks=(
                EvalCheck(
                    EvalCheckType.FILE_EQUALS,
                    "names.txt",
                    "# Active users\nalice\nbob\nzoe\n",
                ),
            ),
        ),
    )


def seed_workspace(task: EvalTask, workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for relative, content in task.seed_files.items():
        path = _workspace_path(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def evaluate_task(task: EvalTask, workspace: Path) -> list[dict[str, Any]]:
    return [_evaluate_check(check, workspace) for check in task.checks]


def _evaluate_check(check: EvalCheck, workspace: Path) -> dict[str, Any]:
    path = _workspace_path(workspace, check.path)
    actual: Any = None
    error: str | None = None

    try:
        content = path.read_text(encoding="utf-8")
        if check.kind == EvalCheckType.FILE_EQUALS:
            actual = content
            passed = content == check.expected
        elif check.kind == EvalCheckType.FILE_CONTAINS:
            actual = content
            passed = str(check.expected) in content
        elif check.kind == EvalCheckType.FILE_NOT_CONTAINS:
            actual = content
            passed = str(check.expected) not in content
        elif check.kind == EvalCheckType.JSON_EQUALS:
            data = json.loads(content)
            actual = _json_value(data, check.json_path or "")
            passed = actual == check.expected
        else:
            raise ValueError(f"unsupported eval check: {check.kind}")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        passed = False
        error = str(exc)

    return {
        "kind": check.kind.value,
        "path": check.path,
        "json_path": check.json_path,
        "passed": passed,
        "expected": check.expected,
        "actual": _preview(actual),
        "error": error,
    }


def _workspace_path(workspace: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"eval path must be workspace-relative: {relative}")
    return workspace.joinpath(*pure.parts)


def _json_value(data: Any, path: str) -> Any:
    value = data
    for part in path.split(".") if path else ():
        if not isinstance(value, dict):
            raise TypeError(f"{part} is not inside an object")
        value = value[part]
    return value


def _preview(value: Any, limit: int = 500) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"
