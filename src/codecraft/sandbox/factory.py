from __future__ import annotations

import platform
import shutil

from codecraft.sandbox.backend import (
    SandboxBackend,
    SandboxBackendError,
    SandboxBackendType,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)
from codecraft.sandbox.bubblewrap import BubblewrapSandboxBackend
from codecraft.sandbox.docker import DockerSandboxBackend, DockerSandboxConfig
from codecraft.sandbox.process import ProcessSandboxBackend
from codecraft.sandbox.seatbelt import SeatbeltSandboxBackend


class UnavailableSandboxBackend(SandboxBackend):
    name = "unavailable"
    isolation = "none"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        raise SandboxBackendError(self.reason)


def build_sandbox_backend(
    backend_type: SandboxBackendType,
    docker: DockerSandboxConfig | None = None,
) -> SandboxBackend:
    if backend_type == SandboxBackendType.AUTO:
        system = platform.system()
        if system == "Darwin":
            return SeatbeltSandboxBackend()
        if system == "Linux":
            executable = shutil.which("bwrap")
            if executable:
                return BubblewrapSandboxBackend(executable=executable)
            return UnavailableSandboxBackend(
                "bubblewrap is required for the automatic Linux sandbox; "
                "install bwrap or explicitly configure backend='process'"
            )
        return UnavailableSandboxBackend(
            f"no automatic OS sandbox is available for {system}; "
            "explicitly configure backend='process' to run without isolation"
        )
    if backend_type == SandboxBackendType.SEATBELT:
        return SeatbeltSandboxBackend()
    if backend_type == SandboxBackendType.BUBBLEWRAP:
        return BubblewrapSandboxBackend(executable=shutil.which("bwrap") or "bwrap")
    if backend_type == SandboxBackendType.DOCKER:
        return DockerSandboxBackend(docker)
    return ProcessSandboxBackend()
