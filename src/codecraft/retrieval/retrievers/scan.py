from __future__ import annotations

from codecraft.retrieval.files import (
    display_path,
    is_inside_workspace,
    iter_workspace_files,
    looks_binary,
)
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

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        files = (
            [request.root]
            if request.root.is_file()
            else iter_workspace_files(request.root)
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

            if not is_inside_workspace(file_path, request.workspace_roots):
                skipped["escaped"] += 1
                continue

            scanned_file_count += 1
            visible_path = display_path(file_path, request.workspace_roots)
            if request.mode in {"both", "path"}:
                candidate_path = (
                    visible_path if request.case_sensitive else visible_path.casefold()
                )
                if query in candidate_path:
                    matches.append(RetrievalMatch(type="path", path=visible_path))
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
            if looks_binary(raw):
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
                        path=visible_path,
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

    @staticmethod
    def _trim_line(line: str, max_chars: int = 240) -> str:
        normalized = line.strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1]}..."
