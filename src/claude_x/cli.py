"""Command line entry point.

Phase 0 ships the skeleton: global --dry-run, config inspection, version. The
commands that touch the network arrive in Phase 1 (auth, client) and Phase 2
(post). Dry-run defaults to ON and stays that way until posting is signed off,
so no command can spend money or publish by accident before then.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, auth
from .client import XClient
from .config import REDIRECT_URI, SCOPES, Config, load_config
from .errors import AuthError, ClaudeXError

app = typer.Typer(
    name="claude-x",
    help="Claude-drafted posts and reply suggestions for X. You approve everything.",
    no_args_is_help=True,
    add_completion=False,
)

auth_app = typer.Typer(help="Authorise this tool against your X account.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")

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


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="Open the consent page automatically.",
        ),
    ] = True,
) -> None:
    """Authorise via your browser and store the resulting tokens.

    Runs for real even in dry-run mode — logging in costs nothing, and a dry run
    with no credentials would be useless.
    """
    config = get_config(ctx)
    config.require_client_id()

    console.print(f"Listening on [bold]{REDIRECT_URI}[/bold] for the redirect.")

    def show_url(url: str) -> None:
        if open_browser:
            console.print("Opening the X consent screen in your browser…")
        else:
            console.print("Open this URL to authorise:\n")
            console.print(url)

    tokens = auth.login(config, open_browser=open_browser, on_url=show_url)

    # Verify against the live API regardless of --dry-run: a login that can't
    # actually call anything isn't a successful login.
    with XClient(replace(config, dry_run=False)) as client:
        me = client.get_me()["data"]

    console.print(
        f"[green]Authorised[/green] as [bold]@{me['username']}[/bold] "
        f"with scopes: {tokens.scope or ' '.join(SCOPES)}"
    )


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """Show whether valid credentials are stored, without printing them."""
    config = get_config(ctx)
    stored = auth.TokenStore(config).load()

    if stored is None:
        console.print("[yellow]Not authenticated.[/yellow] Run `claude-x auth login`.")
        raise typer.Exit(code=1)

    state = "[red]expired[/red]" if stored.is_expired else "[green]valid[/green]"
    refreshable = "yes" if stored.refresh_token else "no"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("access token", state)
    table.add_row("refreshable", refreshable)
    table.add_row("scopes", stored.scope or "unknown")
    console.print(table)

    if config.dry_run:
        console.print("\n[dim]Dry run: skipping the live identity check.[/dim]")
        return

    try:
        with XClient(config) as client:
            me = client.get_me()["data"]
        console.print(f"\nAuthenticated as [bold]@{me['username']}[/bold]")
    except (AuthError, ClaudeXError) as exc:
        console.print(f"\n[red]Stored tokens did not work:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    """Delete the stored tokens from this machine."""
    auth.logout(get_config(ctx))
    console.print("Stored tokens deleted.")


def run() -> None:
    """Wrapper that renders deliberate errors without a traceback."""
    try:
        app()
    except ClaudeXError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    run()
