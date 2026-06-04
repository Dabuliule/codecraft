from __future__ import annotations

from pathlib import Path

from codecraft.core.errors import WorkspaceAccessError


class WorkspaceGuard:
    def __init__(self, workspace_roots: list[Path]) -> None:
        if not workspace_roots:
            raise ValueError("workspace_roots must not be empty")
        self.workspace_roots = [path.expanduser().resolve() for path in workspace_roots]

    def resolve_read_path(self, path: str, cwd: Path) -> Path:
        resolved = self._resolve(path, cwd)
        self.assert_inside_workspace(resolved)
        return resolved

    def resolve_write_path(self, path: str, cwd: Path) -> Path:
        resolved = self._resolve(path, cwd)
        self.assert_inside_workspace(resolved)
        return resolved

    def assert_inside_workspace(self, path: Path) -> None:
        resolved = path.expanduser().resolve(strict=False)
        for root in self.workspace_roots:
            if resolved == root or root in resolved.parents:
                return

        raise WorkspaceAccessError(
            "path is outside workspace",
            code="workspace_access_denied",
            suggestion="Use a path inside the configured workspace roots.",
            metadata={"path": str(path)},
        )

    @staticmethod
    def _resolve(path: str, cwd: Path) -> Path:
        if not path:
            raise WorkspaceAccessError(
                "path must not be empty",
                code="workspace_path_empty",
            )

        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return candidate.resolve(strict=False)
