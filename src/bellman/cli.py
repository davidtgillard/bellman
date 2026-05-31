"""Bellman command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pyfits.result import Err

from bellman import layout
from bellman._version import version_string
from bellman.errors import BellmanLayoutError
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap
from bellman.plugin.cli import register_plugin_command
from bellman.roadmap import load
from bellman.update import maybe_notify_update, run_update_command
from bellman.validate import validate_roadmap

app = typer.Typer(
    name="bellman",
    help="Markdown-first roadmap planning on pyfits.",
    no_args_is_help=True,
)


@app.callback()
def _cli_entry(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand != "update":
        maybe_notify_update(ctx)


def _root(path: Path | None) -> Path:
    try:
        return layout.discover_roadmap_root(path)
    except BellmanLayoutError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(code=1) from exc


def _apply_graph_sync(root: Path, *, prune: bool = False) -> None:
    """Sync markdown roadmap into pyfits after a layout mutation."""
    if not libfits_available():
        typer.echo("Note: libfits not found; graph not updated.", err=True)
        return
    result = sync_roadmap(root, prune=prune)
    if isinstance(result, Err):
        typer.echo(f"Graph sync failed: {result.err_value}", err=True)
        raise typer.Exit(code=1)
    typer.echo("Graph sync passed.")


@app.command()
def init(
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
) -> None:
    """Initialize roadmap directories and pyfits repository."""
    root = layout.roadmap_root(path)
    layout.ensure_roadmap_dirs(root)
    typer.echo(f"Initialized roadmap at {root}")
    if libfits_available():
        init_result = init_pyfits_repo(root)
        if isinstance(init_result, Err):
            typer.echo(
                f"Warning: graph bootstrap failed: {init_result.err_value}",
                err=True,
            )
        else:
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
    except (BellmanLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root)


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
    except (BellmanLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root)


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
    except (BellmanLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root)


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
    except (BellmanLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root)


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
    except BellmanLayoutError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root, prune=True)


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
    except (BellmanLayoutError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _apply_graph_sync(root)


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

    result = validate_roadmap(roadmap)
    if result.errors:
        for err in result.errors:
            typer.echo(err.format(), err=True)
        raise typer.Exit(code=1)

    for warn in result.warnings:
        typer.echo(f"warning: {warn.format()}", err=True)

    if result.warnings:
        count = len(result.warnings)
        typer.echo(f"Markdown validation passed with {count} warning(s).")
    else:
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
    """Check for and install a newer bellman binary from the dev release."""
    run_update_command(check_only=check_only)


@app.command()
def version() -> None:
    """Print the installed bellman version."""
    typer.echo(version_string())


register_plugin_command(app)


def main() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    main()
