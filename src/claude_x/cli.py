"""Command line entry point.

Phase 0 ships the skeleton: global --dry-run, config inspection, version. The
commands that touch the network arrive in Phase 1 (auth, client) and Phase 2
(post). Dry-run defaults to ON and stays that way until posting is signed off,
so no command can spend money or publish by accident before then.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import REDIRECT_URI, SCOPES, Config, load_config
from .errors import ClaudeXError

app = typer.Typer(
    name="claude-x",
    help="Claude-drafted posts and reply suggestions for X. You approve everything.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


@app.callback()
def main(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--live",
            help="Dry run performs no network calls and spends nothing. On by default.",
        ),
    ] = True,
) -> None:
    """Load configuration once and hand it to whichever command runs."""
    ctx.obj = load_config(dry_run=dry_run)


def get_config(ctx: typer.Context) -> Config:
    config = ctx.find_object(Config)
    if config is None:  # pragma: no cover - only reachable via misuse
        raise ClaudeXError("Configuration was not initialised.")
    return config


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"claude-x {__version__}")


@app.command(name="config")
def show_config(ctx: typer.Context) -> None:
    """Show resolved configuration. Credential values are never printed."""
    config = get_config(ctx)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("mode", "[yellow]dry run[/yellow]" if config.dry_run else "[red]live[/red]")
    table.add_row("client id", "set" if config.client_id else "[red]not set[/red]")
    table.add_row(
        "client secret",
        "set" if config.client_secret else "not set (expected for a Native App)",
    )
    table.add_row("data dir", str(config.data_dir))
    table.add_row("redirect uri", REDIRECT_URI)
    table.add_row("scopes", " ".join(SCOPES))
    console.print(table)


def run() -> None:
    """Wrapper that renders deliberate errors without a traceback."""
    try:
        app()
    except ClaudeXError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    run()
