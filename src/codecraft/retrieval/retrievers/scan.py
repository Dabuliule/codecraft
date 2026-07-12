from __future__ import annotations

from pathlib import Path

from codecraft.retrieval.models import (
    RetrievalMatch,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStats,
)
from codecraft.retrieval.retrievers.base import Retriever


class ScanRetriever(Retriever):
    """Deterministic path and substring retrieval without a persistent index."""

    name = "scan"
    skipped_names = frozenset(
        {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
            "venv",
        }
    )

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        files = (
            [request.root] if request.root.is_file() else self._iter_files(request.root)
        )
        query = request.query if request.case_sensitive else request.query.casefold()
        matches: list[RetrievalMatch] = []
        skipped = {"binary": 0, "large": 0, "escaped": 0}
        scanned_file_count = 0
        read_file_count = 0
        scanned_bytes = 0

        for file_path in files:
            if len(matches) >= request.max_results:
                break

            if not self._is_safe_file(file_path, request.workspace_roots):
                skipped["escaped"] += 1
                continue

            scanned_file_count += 1
            display_path = self._display_path(file_path, request.workspace_roots)
            if request.mode in {"both", "path"}:
                candidate_path = (
                    display_path if request.case_sensitive else display_path.casefold()
                )
                if query in candidate_path:
                    matches.append(RetrievalMatch(type="path", path=display_path))
                    if len(matches) >= request.max_results:
                        break

            if request.mode not in {"both", "content"}:
                continue

            stat = file_path.stat()
            if stat.st_size > request.max_file_bytes:
                skipped["large"] += 1
                continue

            try:
                raw = file_path.read_bytes()
            except OSError:
                continue

            read_file_count += 1
            scanned_bytes += len(raw)
            if self._looks_binary(raw):
                skipped["binary"] += 1
                continue

            text = raw.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                candidate_line = line if request.case_sensitive else line.casefold()
                if query not in candidate_line:
                    continue

                matches.append(
                    RetrievalMatch(
                        type="content",
                        path=display_path,
                        line=line_number,
                        snippet=self._trim_line(line),
                    )
                )
                if len(matches) >= request.max_results:
                    break

        return RetrievalResponse(
            matches=tuple(matches),
            stats=RetrievalStats(
                candidate_file_count=len(files),
                scanned_file_count=scanned_file_count,
                read_file_count=read_file_count,
                scanned_bytes=scanned_bytes,
                skipped=skipped,
            ),
            truncated=len(matches) >= request.max_results,
        )

    @classmethod
    def _iter_files(cls, root: Path) -> list[Path]:
        return sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and not cls._has_skipped_part(path.relative_to(root))
        )

    @classmethod
    def _has_skipped_part(cls, relative: Path) -> bool:
        return any(part in cls.skipped_names for part in relative.parts)

    @staticmethod
    def _is_safe_file(path: Path, workspace_roots: tuple[Path, ...]) -> bool:
        resolved = path.resolve(strict=False)
        return any(
            resolved == root or root in resolved.parents for root in workspace_roots
        )

    @staticmethod
    def _looks_binary(raw: bytes) -> bool:
        return b"\0" in raw[:4096]

    @staticmethod
    def _trim_line(line: str, max_chars: int = 240) -> str:
        normalized = line.strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1]}..."

    @staticmethod
    def _display_path(path: Path, workspace_roots: tuple[Path, ...]) -> str:
        resolved = path.resolve(strict=False)
        for root in sorted(
            workspace_roots, key=lambda item: len(item.parts), reverse=True
        ):
            try:
                return str(resolved.relative_to(root))
            except ValueError:
                continue
        return str(path)
