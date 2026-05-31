"""Background update check on CLI entry."""

from __future__ import annotations

import typer

from bellman.update.check import check_for_update, should_run_background_check
from bellman.update.settings import load_settings
from bellman.update.state import BellmanState


def maybe_notify_update(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand == "update":
        return

    settings = load_settings()
    state = BellmanState.load()
    if not should_run_background_check(state, settings):
        return

    result = check_for_update(settings=settings, state=state, record_check=True)
    if result.kind == "update_available":
        typer.echo(
            "A new version of bellman is available. Run: bellman update",
            err=True,
        )
