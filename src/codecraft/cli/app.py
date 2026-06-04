from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def exec(
    task: str = typer.Argument(..., help="User task to submit to Codecraft."),
) -> None:
    raise typer.BadParameter(
        "codecraft exec will be connected after AgentThread/Session/Turn land."
    )


@app.command()
def chat() -> None:
    raise typer.BadParameter(
        "codecraft chat will be connected after AgentThread/Session/Turn land."
    )


@app.command()
def resume(
    last: bool = typer.Option(False, "--last", help="Resume the latest session."),
) -> None:
    raise typer.BadParameter(
        "codecraft resume will be connected after Session reconstruction lands."
    )


@app.command()
def sessions() -> None:
    raise typer.BadParameter(
        "codecraft sessions will be connected after SessionStore listing lands."
    )


if __name__ == "__main__":
    app()
