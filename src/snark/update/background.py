"""Background update check on CLI entry."""

from __future__ import annotations

import typer

from snark.update.check import check_for_update, should_run_background_check
from snark.update.settings import load_settings
from snark.update.state import SnarkState


def maybe_notify_update(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand == "update":
        return

    settings = load_settings()
    state = SnarkState.load()
    if not should_run_background_check(state, settings):
        return

    result = check_for_update(settings=settings, state=state, record_check=True)
    if result.kind == "update_available":
        typer.echo(
            "A new version of snark is available. Run: snark update",
            err=True,
        )
