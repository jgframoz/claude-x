"""Command line entry point.

Phase 0 ships the skeleton: global --dry-run, config inspection, version. The
commands that touch the network arrive in Phase 1 (auth, client) and Phase 2
(post). Dry-run defaults to ON and stays that way until posting is signed off,
so no command can spend money or publish by accident before then.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, auth, mentions, policy, triage, voice
from .client import XClient
from .config import (
    COST_PER_POST_USD,
    COST_PER_POST_WITH_LINK_USD,
    REDIRECT_URI,
    SCOPES,
    Config,
    load_config,
)
from .errors import AuthError, ClaudeXError
from .publisher import (
    APPROVAL_HUMAN_FLAG,
    APPROVAL_INTERACTIVE,
    APPROVAL_RELAYED,
    PostLog,
    Publisher,
)

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


def _read_draft(text: str | None, file: Path | None) -> str:
    """Take the draft from --text, --file, or stdin, in that order."""
    if text is not None and file is not None:
        raise ClaudeXError("Pass --text or --file, not both.")
    if text is not None:
        return text
    if file is not None:
        if not file.is_file():
            raise ClaudeXError(f"No such file: {file}")
        return file.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ClaudeXError("Nothing to post. Use --text, --file, or pipe the draft on stdin.")


def _render_preview(parts: list[str]) -> float:
    """Show what will be published and return the total cost."""
    total = sum(policy.estimate_cost(part) for part in parts)

    for index, part in enumerate(parts, start=1):
        length = policy.weighted_length(part)
        heading = f"part {index}/{len(parts)}" if len(parts) > 1 else "post"
        over = length > policy.MAX_WEIGHTED_LENGTH
        console.print(
            Panel(
                part,
                title=heading,
                subtitle=(
                    f"[{'red' if over else 'dim'}]{length}/{policy.MAX_WEIGHTED_LENGTH}"
                    f"[/{'red' if over else 'dim'}]"
                ),
                subtitle_align="right",
                border_style="red" if over else "cyan",
            )
        )
        if policy.contains_link(part):
            console.print(
                f"  [yellow]contains a link[/yellow] — costs "
                f"${COST_PER_POST_WITH_LINK_USD:.2f} instead of "
                f"${COST_PER_POST_USD:.3f}"
            )

    console.print(f"\nEstimated cost: [bold]${total:.3f}[/bold]")
    return total


def _establish_approval(*, yes: bool, approved: bool) -> str:
    """Work out how this publish was approved, or refuse to proceed.

    No flag can prove a human agreed; the caller asserts it. What this buys is
    an unambiguous instruction for an agent (which would otherwise have to
    choose between a rule saying "never pass --yes" and a prompt it cannot
    answer) and a recorded route in the history.
    """
    if approved:
        return APPROVAL_RELAYED
    if yes:
        return APPROVAL_HUMAN_FLAG

    if not sys.stdin.isatty():
        # Hanging on a prompt nobody can answer is the worst outcome here.
        raise ClaudeXError(
            "Refusing to publish: no confirmation is possible without a terminal.\n"
            "If you are a person scripting this, pass --yes.\n"
            "If you are an agent, pass --approved, and only when the user has "
            "approved this exact text in the current turn."
        )

    console.print()
    answer = typer.prompt("Type 'post' to publish, anything else to cancel", default="")
    if answer.strip().casefold() != "post":
        console.print("[dim]Cancelled. Nothing was sent.[/dim]")
        raise typer.Exit(code=1)
    return APPROVAL_INTERACTIVE


@app.command()
def post(
    ctx: typer.Context,
    text: Annotated[str | None, typer.Option("--text", "-t", help="Draft text.")] = None,
    file: Annotated[
        Path | None, typer.Option("--file", "-f", help="Read the draft from a file.")
    ] = None,
    thread: Annotated[
        bool,
        typer.Option("--thread", help="Split the draft into a thread on lines containing '---'."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Skip the prompt because you, a human, already decided. "
            "Agents: use --approved instead.",
        ),
    ] = False,
    approved: Annotated[
        bool,
        typer.Option(
            "--approved",
            help="For agents: the user approved this exact text in the current "
            "conversation turn. Recorded in the history as agent-relayed.",
        ),
    ] = False,
) -> None:
    """Publish a draft, after showing you exactly what will go out.

    Dry run by default: you'll see the preview and the cost, and nothing is
    sent. Add --live to actually publish.
    """
    config = get_config(ctx)
    draft = _read_draft(text, file)

    parts = policy.split_thread(draft) if thread else [draft.strip()]
    if not parts:
        raise ClaudeXError("The draft is empty.")

    # Validate before previewing, and in dry run too. Otherwise a rehearsal
    # looks clean and only the live attempt fails, which is the worst moment
    # to discover a problem.
    for part in parts:
        policy.check_length(part)
        policy.check_style(part)

    _render_preview(parts)

    if config.dry_run:
        console.print(
            "\n[yellow]Dry run — nothing was sent.[/yellow] Re-run with "
            "[bold]--live[/bold] to publish."
        )
        return

    approval = _establish_approval(yes=yes, approved=approved)

    with Publisher(config) as publisher:
        published = (
            publisher.publish_thread(parts, approval=approval)
            if len(parts) > 1
            else [publisher.publish(parts[0], approval=approval)]
        )

    console.print()
    for item in published:
        console.print(f"[green]published[/green] {item.url}")
    spent = sum(item.cost_usd for item in published)
    console.print(f"[dim]spent ~${spent:.3f}[/dim]")


@app.command(name="mentions")
def show_mentions(
    ctx: typer.Context,
    fetch: Annotated[
        bool,
        typer.Option(
            "--fetch/--no-fetch",
            help="Ask X for new mentions. Reads are billed, so --no-fetch just "
            "shows what is already stored.",
        ),
    ] = True,
    show_all: Annotated[
        bool, typer.Option("--all", help="Include mentions already marked handled.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Machine-readable output, for agents.")
    ] = False,
    spam: Annotated[
        bool,
        typer.Option("--spam", help="Show only what was set aside as likely spam."),
    ] = False,
    mark_handled: Annotated[
        str | None,
        typer.Option("--mark-handled", metavar="ID", help="Mark a mention as dealt with."),
    ] = None,
    forget: Annotated[
        str | None,
        typer.Option(
            "--forget",
            metavar="ID",
            help="Delete a stored mention locally, e.g. once it is deleted on X.",
        ),
    ] = None,
) -> None:
    """Show posts mentioning you, so replies can be drafted for you to send.

    This command never sends anything. Automated replies to other people need
    prior written approval from X, so you send them yourself.
    """
    config = get_config(ctx)
    log = mentions.MentionLog(config)

    if mark_handled:
        found = log.mark_handled(mark_handled)
        console.print(
            f"Marked {mark_handled} as handled."
            if found
            else f"[yellow]No stored mention with id {mark_handled}.[/yellow]"
        )
        return

    if forget:
        removed = log.forget(forget)
        console.print(f"Removed {removed} stored record(s) for {forget}.")
        return

    fetched: list[mentions.Mention] = []
    if fetch:
        with XClient(config) as client:
            fetched = mentions.fetch_new(config, client)
        if config.dry_run:
            console.print("[dim]Dry run: fixture data, nothing fetched and nothing stored.[/dim]\n")
        elif fetched:
            console.print(f"[green]{len(fetched)} new.[/green]\n")

    # Dry runs store nothing, so show what the fetch returned rather than the log.
    stored = log.all() if show_all else log.unhandled()
    items = fetched if (config.dry_run and fetch) else stored

    # Sort rather than delete: a wrongly buried mention costs a conversation.
    triaged = [(item, *triage.classify(item.text)) for item in items]
    junk = [(item, reason) for item, is_spam, reason in triaged if is_spam]
    real = [item for item, is_spam, _ in triaged if not is_spam]

    if spam:
        if not junk:
            console.print("[dim]Nothing set aside.[/dim]")
            return
        for item, reason in junk:
            console.print(f"[dim]@{item.username} · {reason}[/dim]")
            console.print(f"[dim]  {item.url}[/dim]")
            console.print(f"[dim]  {item.text[:120]}[/dim]\n")
        return

    items = real

    if as_json:
        # Plain stdout: this output is for an agent to parse.
        print(
            json.dumps(
                [{**asdict(item), "url": item.url} for item in real],
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if not items:
        console.print("[dim]No mentions waiting.[/dim]")
        if junk:
            console.print(f"[dim]{len(junk)} set aside as likely spam (--spam to see).[/dim]")
        return

    for item in items:
        flag = " [dim](handled)[/dim]" if item.handled else ""
        console.print(f"[bold]@{item.username}[/bold] · {item.created_at}{flag}")
        console.print(f"  {item.url}")
        console.print(f"  id: {item.id}")
        console.print(f"  {item.text}\n")

    if junk:
        console.print(f"[dim]{len(junk)} set aside as likely spam (--spam to see).[/dim]")
    console.print(
        "[dim]Drafts only. Send replies yourself, then run "
        "`claude-x mentions --mark-handled <id>`.[/dim]"
    )


@app.command(name="voice")
def show_voice(
    ctx: typer.Context,
    path_only: Annotated[
        bool, typer.Option("--path", help="Print the file location instead of its contents.")
    ] = False,
) -> None:
    """Print the voice guide drafts should follow.

    Created from a template on first use. Works from any directory, which is why
    the skill reads it through this command rather than by relative path.
    """
    config = get_config(ctx)
    if path_only:
        console.print(str(voice.ensure_voice(config)))
        return
    # Plain stdout: this is meant to be read by an agent, not rendered.
    print(voice.read_voice(config))


@app.command()
def history(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", help="How many to show.")] = 10,
) -> None:
    """Show what this tool has published."""
    records = PostLog(get_config(ctx)).all()
    if not records:
        console.print("[dim]Nothing published yet.[/dim]")
        return

    table = Table(box=None, padding=(0, 2))
    table.add_column("when", style="dim")
    table.add_column("text")
    table.add_column("cost", justify="right", style="dim")
    table.add_column("approved", style="dim")

    for record in records[-limit:]:
        preview = record.get("text", "").replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "…"
        marker = " [yellow](dry)[/yellow]" if record.get("dry_run") else ""
        table.add_row(
            record.get("posted_at", "?"),
            preview + marker,
            f"${record.get('cost_usd', 0):.3f}",
            "" if record.get("dry_run") else record.get("approval", "unrecorded"),
        )
    console.print(table)

    live = [record for record in records if not record.get("dry_run")]
    spent = sum(record.get("cost_usd", 0) for record in live)
    console.print(
        f"\n[dim]{len(live)} published, ${spent:.2f} spent on posting "
        f"(reads are billed separately by X).[/dim]"
    )


def run() -> None:
    """Wrapper that renders deliberate errors without a traceback.

    Exits via sys.exit rather than typer.Exit: outside a command invocation
    typer.Exit is just an uncaught exception, which is the traceback this
    wrapper exists to prevent.
    """
    try:
        app()
    except ClaudeXError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    run()
