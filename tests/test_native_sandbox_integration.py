from __future__ import annotations

import asyncio
import os
import platform

import pytest

from codecraft.sandbox import (
    SandboxExecutionRequest,
    SandboxMode,
    SeatbeltSandboxBackend,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        platform.system() != "Darwin"
        or os.environ.get("CODECRAFT_RUN_NATIVE_SANDBOX_TESTS") != "1",
        reason="set CODECRAFT_RUN_NATIVE_SANDBOX_TESTS=1 on macOS",
    ),
]


def test_seatbelt_enforces_write_network_and_environment_boundaries(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    monkeypatch.setenv("DASHSCOPE_API_KEY", "must-not-leak")
    request = SandboxExecutionRequest(
        command=(
            "printf allowed > inside.txt; "
            f"(printf denied > {outside}) || true; "
            "printf key=${DASHSCOPE_API_KEY-unset}; "
            "python -c 'import socket; socket.socket().bind((\"127.0.0.1\", 0))' "
            ">/dev/null 2>&1 && printf ' network=open' || printf ' network=blocked'"
        ),
        cwd=workspace,
        workspace_roots=(workspace,),
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        network_access=False,
        timeout_seconds=30,
    )

    result = asyncio.run(SeatbeltSandboxBackend().execute(request))

    assert result.exit_code == 0, result.stderr.decode("utf-8", errors="replace")
    assert (workspace / "inside.txt").read_text(encoding="utf-8") == "allowed"
    assert not outside.exists()
    assert result.stdout == b"key=unset network=blocked"
    assert result.metadata["isolation"] == "os"
