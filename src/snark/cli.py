"""Snark command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pyfits.result import Err

from snark import layout
from snark._version import version_string
from snark.errors import SnarkLayoutError
from snark.graph.sync import libfits_available, sync_roadmap
from snark.plugin.cli import register_plugin_command
from snark.roadmap import load
from snark.update import maybe_notify_update, run_update_command
from snark.validate import validate_roadmap

app = typer.Typer(
    name="snark",
    help="Markdown-first roadmap planning on pyfits.",
    no_args_is_help=True,
)


@app.callback()
def _cli_entry(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand != "update":
        maybe_notify_update(ctx)


def _root(path: Path | None) -> Path:
    return layout.roadmap_root(path)


@app.command()
def init(
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
) -> None:
    """Initialize roadmap directories and pyfits repository."""
    root = _root(path)
    layout.ensure_roadmap_dirs(root)
    typer.echo(f"Initialized roadmap at {root}")
    if libfits_available():
        sync_result = sync_roadmap(root)
        if isinstance(sync_result, Err):
            typer.echo(
                f"Warning: graph bootstrap failed: {sync_result.err_value}",
                err=True,
            )
    else:
        typer.echo(
            "Note: libfits not found; run validate after installing libfits.",
            err=True,
        )


create_app = typer.Typer(help="Create roadmap entities.")
app.add_typer(create_app, name="create")


@create_app.command("initiative")
def create_initiative(
    name: Annotated[str, typer.Argument(help="Initiative name (kebab-case)")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
) -> None:
    """Create an initiative markdown file."""
    root = _root(path)
    layout.ensure_roadmap_dirs(root)
    try:
        created = layout.create_initiative(root, name)
        typer.echo(f"Created {created}")
    except (SnarkLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@create_app.command("project")
def create_project(
    name: Annotated[str, typer.Argument(help="Project name (kebab-case)")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
) -> None:
    """Create a project folder."""
    root = _root(path)
    layout.ensure_roadmap_dirs(root)
    try:
        created = layout.create_project(root, name)
        typer.echo(f"Created {created}")
    except (SnarkLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@create_app.command("milestone")
def create_milestone(
    name: Annotated[str, typer.Argument(help="Milestone name (kebab-case)")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
) -> None:
    """Create a milestone markdown file."""
    root = _root(path)
    layout.ensure_roadmap_dirs(root)
    try:
        created = layout.create_milestone(root, name)
        typer.echo(f"Created {created}")
    except (SnarkLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@create_app.command("goal")
def create_goal(
    name: Annotated[str, typer.Argument(help="Goal name (kebab-case)")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
) -> None:
    """Create a goal markdown file."""
    root = _root(path)
    layout.ensure_roadmap_dirs(root)
    try:
        created = layout.create_goal(root, name)
        typer.echo(f"Created {created}")
    except (SnarkLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def delete(
    name: Annotated[str, typer.Argument(help="Entity natural name")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
    force: Annotated[bool, typer.Option("--force", help="Force delete")] = False,
) -> None:
    """Delete an initiative, project, milestone, or goal."""
    root = _root(path)
    try:
        layout.delete_entity(root, name, force=force)
        typer.echo(f"Deleted {name}")
    except SnarkLayoutError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def promote(
    name: Annotated[str, typer.Argument(help="Initiative name to promote")],
    path: Annotated[Path | None, typer.Option("--path", help="Roadmap root")] = None,
) -> None:
    """Promote an initiative to a project."""
    root = _root(path)
    try:
        created = layout.promote_initiative(root, name)
        typer.echo(f"Promoted to {created}")
    except (SnarkLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def validate(
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
    sync: Annotated[
        bool,
        typer.Option("--sync/--no-sync", help="Sync to pyfits graph"),
    ] = True,
    prune: Annotated[
        bool,
        typer.Option("--prune", help="Prune stale graph objects"),
    ] = False,
) -> None:
    """Validate roadmap markdown and optionally sync to pyfits."""
    root = _root(path)
    try:
        roadmap = load(root)
    except (ValueError, OSError) as exc:
        typer.echo(f"load error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_roadmap(roadmap)
    if errors:
        for err in errors:
            typer.echo(err.format(), err=True)
        raise typer.Exit(code=1)

    typer.echo("Markdown validation passed.")

    if sync:
        if not libfits_available():
            typer.echo(
                "Skipping graph sync: libfits not available.",
                err=True,
            )
            return
        sync_result = sync_roadmap(root, prune=prune)
        if isinstance(sync_result, Err):
            typer.echo(f"Graph sync failed: {sync_result.err_value}", err=True)
            raise typer.Exit(code=1)
        typer.echo("Graph sync and libfits validation passed.")


@app.command()
def update(
    check_only: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Check for updates without installing (exit 1 if available)",
        ),
    ] = False,
) -> None:
    """Check for and install a newer snark binary from the dev release."""
    run_update_command(check_only=check_only)


@app.command()
def version() -> None:
    """Print the installed snark version."""
    typer.echo(version_string())


register_plugin_command(app)


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
