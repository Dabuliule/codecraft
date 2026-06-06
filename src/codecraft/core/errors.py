from __future__ import annotations

from typing import Any


class CodecraftError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        suggestion: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.suggestion = suggestion
        self.metadata = metadata or {}
        super().__init__(message)


class SessionError(CodecraftError):
    pass


class SessionRestoreError(CodecraftError):
    pass


class ToolNotFoundError(CodecraftError):
    pass


class ToolExecutionError(CodecraftError):
    pass


class WorkspaceAccessError(CodecraftError):
    pass


class ApprovalDeniedError(CodecraftError):
    pass


class ModelProviderError(CodecraftError):
    pass


class CommandDeniedError(CodecraftError):
    pass
