from __future__ import annotations

from pathlib import Path

SKIPPED_NAMES = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".uv-cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def iter_workspace_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and is_inside_workspace(path, (root,))
        and not any(part in SKIPPED_NAMES for part in path.relative_to(root).parts)
    )


def is_inside_workspace(path: Path, workspace_roots: tuple[Path, ...]) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    return any(
        resolved == root.expanduser().resolve(strict=False)
        or root.expanduser().resolve(strict=False) in resolved.parents
        for root in workspace_roots
    )


def display_path(path: Path, workspace_roots: tuple[Path, ...]) -> str:
    resolved = path.expanduser().resolve(strict=False)
    roots = (root.expanduser().resolve(strict=False) for root in workspace_roots)
    for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
        try:
            return str(resolved.relative_to(root))
        except ValueError:
            continue
    return str(path)


def looks_binary(raw: bytes) -> bool:
    return b"\0" in raw[:4096]
