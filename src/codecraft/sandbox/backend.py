from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from codecraft.sandbox.policy import SandboxMode

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SandboxBackendType(StrEnum):
    LOCAL = "local"
    DOCKER = "docker"


class DockerSandboxConfig(BaseModel):
    image: str = Field(default="codecraft-sandbox:py311", min_length=1)
    cpus: float = Field(default=1.0, gt=0, le=32)
    memory_mb: int = Field(default=1024, ge=64, le=65_536)
    pids_limit: int = Field(default=256, ge=16, le=32_768)
    tmpfs_mb: int = Field(default=256, ge=16, le=8192)
    env_allowlist: list[str] = Field(default_factory=list)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str) -> str:
        if value.startswith("-") or any(character.isspace() for character in value):
            raise ValueError("Docker image must be a reference, not a CLI option")
        return value

    @field_validator("env_allowlist")
    @classmethod
    def validate_env_names(cls, values: list[str]) -> list[str]:
        invalid = [value for value in values if not _ENV_NAME.fullmatch(value)]
        if invalid:
            raise ValueError(f"invalid environment variable names: {invalid}")
        return list(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class SandboxExecutionRequest:
    command: str
    cwd: Path
    workspace_roots: tuple[Path, ...]
    sandbox_mode: SandboxMode
    network_access: bool
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    backend_error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class SandboxBackendError(RuntimeError):
    pass


class SandboxBackend:
    name: str

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        raise NotImplementedError


class LocalSandboxBackend(SandboxBackend):
    name = SandboxBackendType.LOCAL.value

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        try:
            process = await asyncio.create_subprocess_shell(
                request.command,
                cwd=str(request.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SandboxBackendError(f"could not start local command: {exc}") from exc
        stdout, stderr, timed_out = await _communicate(
            process, timeout_seconds=request.timeout_seconds
        )
        return SandboxExecutionResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            metadata={"backend": self.name},
        )


class DockerSandboxBackend(SandboxBackend):
    name = SandboxBackendType.DOCKER.value

    def __init__(
        self,
        config: DockerSandboxConfig | None = None,
        *,
        executable: str = "docker",
    ) -> None:
        self.config = config or DockerSandboxConfig()
        self.executable = executable

    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        container_name = f"codecraft-{uuid4().hex[:16]}"
        command = self.build_command(request, container_name=container_name)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise SandboxBackendError(
                f"Docker executable not found: {self.executable}"
            ) from exc
        except OSError as exc:
            raise SandboxBackendError(f"could not start Docker sandbox: {exc}") from exc

        stdout, stderr, timed_out = await _communicate(
            process, timeout_seconds=request.timeout_seconds
        )
        if timed_out:
            await self._force_remove(container_name)
        backend_error = (
            stderr.decode("utf-8", errors="replace").strip()
            if process.returncode == 125 and not timed_out
            else None
        )
        return SandboxExecutionResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            backend_error=backend_error,
            metadata={
                "backend": self.name,
                "container_name": container_name,
                "image": self.config.image,
                "network_access": request.network_access,
            },
        )

    def build_command(
        self,
        request: SandboxExecutionRequest,
        *,
        container_name: str,
    ) -> list[str]:
        mounts, container_cwd = _workspace_mounts(request)
        command = [
            self.executable,
            "run",
            "--rm",
            "--name",
            container_name,
            "--init",
            "--pull",
            "never",
            "--workdir",
            container_cwd,
            "--memory",
            f"{self.config.memory_mb}m",
            "--cpus",
            str(self.config.cpus),
            "--pids-limit",
            str(self.config.pids_limit),
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,size={self.config.tmpfs_mb}m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--env",
            "HOME=/tmp",
            "--env",
            "XDG_CACHE_HOME=/tmp/.cache",
        ]
        if not request.network_access:
            command.extend(["--network", "none"])
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
        for host_path, container_path, access in mounts:
            if "," in host_path:
                raise SandboxBackendError(
                    "workspace paths containing commas cannot be mounted safely"
                )
            mount = f"type=bind,source={host_path},target={container_path}"
            if access == "ro":
                mount += ",readonly"
            command.extend(["--mount", mount])
        for name in self.config.env_allowlist:
            if name in os.environ:
                command.extend(["--env", name])
        command.extend([self.config.image, "/bin/sh", "-lc", request.command])
        return command

    async def _force_remove(self, container_name: str) -> None:
        try:
            cleanup = await asyncio.create_subprocess_exec(
                self.executable,
                "rm",
                "--force",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(cleanup.wait(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            return


async def _communicate(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: int,
) -> tuple[bytes, bytes, bool]:
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
        return stdout, stderr, False
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return stdout, stderr, True


def _workspace_mounts(
    request: SandboxExecutionRequest,
) -> tuple[list[tuple[str, str, str]], str]:
    roots = tuple(
        dict.fromkeys(root.expanduser().resolve() for root in request.workspace_roots)
    )
    if not roots:
        raise SandboxBackendError("Docker sandbox requires a workspace root")
    resolved_cwd = request.cwd.expanduser().resolve()
    access = "ro" if request.sandbox_mode == SandboxMode.READ_ONLY else "rw"
    mounts: list[tuple[str, str, str]] = []
    mapped_cwd: str | None = None
    ordered_roots = sorted(roots, key=lambda root: len(root.parts), reverse=True)
    target_by_root = {
        root: "/workspace" if len(roots) == 1 else f"/workspaces/{index}"
        for index, root in enumerate(roots)
    }
    for root in roots:
        mounts.append((str(root), target_by_root[root], access))
    for root in ordered_roots:
        try:
            relative = resolved_cwd.relative_to(root)
        except ValueError:
            continue
        base = target_by_root[root]
        mapped_cwd = base if not relative.parts else f"{base}/{relative.as_posix()}"
        break
    if mapped_cwd is None:
        raise SandboxBackendError("command cwd is outside mounted workspaces")
    return mounts, mapped_cwd


def build_sandbox_backend(
    backend_type: SandboxBackendType,
    docker: DockerSandboxConfig | None = None,
) -> SandboxBackend:
    if backend_type == SandboxBackendType.DOCKER:
        return DockerSandboxBackend(docker)
    return LocalSandboxBackend()
