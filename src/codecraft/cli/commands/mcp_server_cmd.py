from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codecraft.cli.options import CodecraftHomeOption
from codecraft.cli.ui import make_console
from codecraft.mcp.server import create_repository_mcp_server


def register_mcp_server_command(app: typer.Typer) -> None:
    @app.command("mcp-server")
    def mcp_server_command(
        workspace: Annotated[
            Path,
            typer.Option(
                "--workspace",
                "-w",
                help="Repository directory exposed by the MCP server.",
            ),
        ] = Path("."),
        codecraft_home: CodecraftHomeOption = Path("~/.codecraft"),
    ) -> None:
        root = workspace.expanduser().resolve()
        if not root.is_dir():
            make_console(stderr=True).print(
                f"Workspace is not a directory: {root}",
                style="error",
                markup=False,
            )
            raise typer.Exit(code=2)
        server = create_repository_mcp_server(
            root,
            codecraft_home=codecraft_home.expanduser().resolve(),
        )
        server.run(transport="stdio")
