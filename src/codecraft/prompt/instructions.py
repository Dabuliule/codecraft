from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstructionLoader:
    """从 workspace 中收集项目级 instructions。

    搜索范围从当前 cwd 一直向上到匹配的 workspace root，支持 AGENTS.md 和
    CODECRAFT.md；越靠近 cwd 的文件越先出现。
    """

    filenames: tuple[str, ...] = ("AGENTS.md", "CODECRAFT.md")
    max_chars: int = 40_000

    def load_project_instructions(
        self, *, cwd: Path, workspace_roots: list[Path]
    ) -> str | None:
        """读取并合并当前目录可见的项目 instructions。"""
        roots = [root.expanduser().resolve() for root in workspace_roots]
        current = cwd.expanduser().resolve()
        matched_root = _find_containing_root(current, roots)
        if matched_root is None:
            return None

        sections: list[str] = []
        for directory in _walk_up(current, matched_root):
            for filename in self.filenames:
                path = directory / filename
                if not path.is_file():
                    continue
                content = _read_text(path)
                if content is None or not content.strip():
                    continue
                sections.append(
                    f"# {path.relative_to(matched_root)}\n\n{content.strip()}"
                )

        if not sections:
            return None

        combined = "\n\n".join(sections)
        if len(combined) <= self.max_chars:
            return combined
        return combined[: self.max_chars] + "\n\n[project instructions truncated]"


def _find_containing_root(path: Path, roots: list[Path]) -> Path | None:
    """找到包含 path 的最深 workspace root。"""
    containing = [root for root in roots if path == root or root in path.parents]
    if not containing:
        return None
    return max(containing, key=lambda root: len(root.parts))


def _walk_up(start: Path, stop: Path) -> list[Path]:
    """返回从 start 到 stop 的目录链，包含两端。"""
    directories = [start]
    current = start
    while current != stop:
        current = current.parent
        directories.append(current)
    return directories


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
