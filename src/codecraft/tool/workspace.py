from __future__ import annotations

from pathlib import Path

from codecraft.core.errors import WorkspaceAccessError


class WorkspaceGuard:
    """把用户传入的路径限制在 workspace_roots 内。

    所有文件读写工具都应先经过这个 guard。它允许不存在的目标路径用于写入，
    但解析后的最终路径仍必须落在 workspace 内。
    """

    def __init__(self, workspace_roots: list[Path]) -> None:
        if not workspace_roots:
            raise ValueError("workspace_roots must not be empty")
        self.workspace_roots = [path.expanduser().resolve() for path in workspace_roots]

    def resolve_read_path(self, path: str, cwd: Path) -> Path:
        """解析读取路径，并确认它没有逃出 workspace。"""
        resolved = self._resolve(path, cwd)
        self.assert_inside_workspace(resolved)
        return resolved

    def resolve_write_path(self, path: str, cwd: Path) -> Path:
        """解析写入路径，并确认它没有逃出 workspace。"""
        resolved = self._resolve(path, cwd)
        self.assert_inside_workspace(resolved)
        return resolved

    def assert_inside_workspace(self, path: Path) -> None:
        """检查路径是否在任一 workspace root 下。"""
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
