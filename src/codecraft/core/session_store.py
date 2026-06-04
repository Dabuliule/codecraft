from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from codecraft.core.errors import SessionError, SessionRestoreError
from codecraft.schema.event import RuntimeEvent, RuntimeEventType
from codecraft.schema.session import SessionConfig, SessionSnapshot, SessionSummary


class SessionStore:
    def __init__(self, codecraft_home: Path) -> None:
        self.codecraft_home = codecraft_home.expanduser().resolve()
        self.sessions_dir = self.codecraft_home / "sessions"
        self._paths: dict[str, Path] = {}

    async def create_session(self, config: SessionConfig) -> Path:
        created_at = config.created_at
        path = (
            self.sessions_dir
            / f"{created_at.year:04d}"
            / f"{created_at.month:02d}"
            / f"{created_at.day:02d}"
            / f"{config.session_id}.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=False)
        self._paths[config.session_id] = path
        return path

    async def append_event(self, event: RuntimeEvent) -> None:
        path = self._path_for_session(event.session_id)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json())
                handle.write("\n")
                handle.flush()
        except Exception as exc:
            raise SessionError(
                "failed to append session event",
                code="session_event_append_failed",
                metadata={"session_id": event.session_id, "path": str(path)},
            ) from exc

    async def load_events(self, session_id: str) -> list[RuntimeEvent]:
        path = self._path_for_session(session_id)
        events: list[RuntimeEvent] = []

        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        events.append(RuntimeEvent.model_validate_json(stripped))
                    except Exception as exc:
                        raise SessionRestoreError(
                            "failed to parse session event",
                            code="session_event_parse_failed",
                            metadata={
                                "session_id": session_id,
                                "path": str(path),
                                "line": line_number,
                            },
                        ) from exc
        except CodecraftFileNotFoundError as exc:
            raise exc
        except OSError as exc:
            raise SessionRestoreError(
                "failed to load session events",
                code="session_events_load_failed",
                metadata={"session_id": session_id, "path": str(path)},
            ) from exc

        self._validate_seq(session_id, events)
        return events

    async def list_sessions(self, cwd: Path | None = None) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        cwd_resolved = cwd.expanduser().resolve() if cwd else None

        for path in self._iter_session_files():
            events = await self.load_events(path.stem)
            if not events:
                summaries.append(
                    SessionSummary(
                        session_id=path.stem,
                        thread_id="",
                        path=path,
                    )
                )
                continue

            first = events[0]
            last = events[-1]
            config = first.payload.get("config")
            if not isinstance(config, dict):
                config = {}
            session_cwd = self._optional_path(config.get("cwd"))

            if cwd_resolved and session_cwd != cwd_resolved:
                continue

            summaries.append(
                SessionSummary(
                    session_id=first.session_id,
                    thread_id=str(config.get("thread_id", "")),
                    path=path,
                    cwd=session_cwd,
                    source=config.get("source"),
                    created_at=first.timestamp,
                    last_event_at=last.timestamp,
                    event_count=len(events),
                )
            )

        return sorted(
            summaries,
            key=lambda summary: (
                summary.last_event_at
                or summary.created_at
                or datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        )

    async def resume_last(self, cwd: Path | None = None) -> SessionSnapshot:
        summaries = await self.list_sessions(cwd=cwd)
        if not summaries:
            raise SessionRestoreError(
                "no session found to resume",
                code="session_not_found",
            )

        return await self.resume(summaries[0].session_id)

    async def resume(self, session_id: str) -> SessionSnapshot:
        events = await self.load_events(session_id)
        if not events:
            raise SessionRestoreError(
                "session contains no events",
                code="session_empty",
                metadata={"session_id": session_id},
            )

        started = events[0]
        if started.type != RuntimeEventType.SESSION_STARTED:
            raise SessionRestoreError(
                "session log must start with session_started",
                code="session_start_event_missing",
                metadata={"session_id": session_id},
            )

        config_data = started.payload.get("config")
        if not isinstance(config_data, dict):
            raise SessionRestoreError(
                "session_started event is missing config payload",
                code="session_config_missing",
                metadata={"session_id": session_id},
            )

        return SessionSnapshot(
            config=SessionConfig.model_validate(config_data),
            events=events,
        )

    def _path_for_session(self, session_id: str) -> Path:
        if session_id in self._paths:
            return self._paths[session_id]

        matches = list(self.sessions_dir.glob(f"**/{session_id}.jsonl"))
        if not matches:
            raise CodecraftFileNotFoundError(
                "session file not found",
                code="session_file_not_found",
                metadata={"session_id": session_id},
            )

        path = matches[0]
        self._paths[session_id] = path
        return path

    def _iter_session_files(self) -> list[Path]:
        if not self.sessions_dir.exists():
            return []
        return sorted(self.sessions_dir.glob("**/*.jsonl"))

    @staticmethod
    def _validate_seq(session_id: str, events: list[RuntimeEvent]) -> None:
        for expected, event in enumerate(events, start=1):
            if event.session_id != session_id:
                raise SessionRestoreError(
                    "session event has mismatched session_id",
                    code="session_id_mismatch",
                    metadata={
                        "expected": session_id,
                        "actual": event.session_id,
                        "seq": event.seq,
                    },
                )

            if event.seq != expected:
                raise SessionRestoreError(
                    "session event sequence is not continuous",
                    code="session_seq_not_continuous",
                    metadata={
                        "session_id": session_id,
                        "expected": expected,
                        "actual": event.seq,
                    },
                )

    @staticmethod
    def _optional_path(value: object) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        return Path(value).expanduser().resolve()


class CodecraftFileNotFoundError(SessionRestoreError):
    pass
