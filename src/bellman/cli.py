"""Bellman command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from pyfits.result import Err
from typer.core import TyperGroup

from bellman import layout
from bellman._version import version_string
from bellman.errors import BellmanLayoutError
from bellman.graph.delta import (
    RegistryDelta,
    RegistryDeltaError,
    compute_registry_delta,
)
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap
from bellman.model import Roadmap
from bellman.plugin.cli import register_plugin_command
from bellman.report.wbs import write_wbs_csv, write_wbs_csv_file
from bellman.report.wbs_tree import write_wbs_tree
from bellman.roadmap import load, load_for_validation
from bellman.update import maybe_notify_update, run_update_command
from bellman.validate import ValidationResult, validate_roadmap

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


def _markdown_validation_result(root: Path) -> tuple[ValidationResult, Roadmap]:
    load_result = load_for_validation(root)
    validation = validate_roadmap(load_result.roadmap)
    return ValidationResult(
        errors=load_result.errors + validation.errors,
        warnings=validation.warnings,
    ), load_result.roadmap


def _emit_validation_result(result: ValidationResult) -> bool:
    """Emit markdown validation messages.

    Returns:
        True when validation errors were reported.
    """
    if result.errors:
        for err in result.errors:
            typer.echo(err.format(), err=True)
        return True

    for warn in result.warnings:
        typer.echo(f"warning: {warn.format()}", err=True)

    if result.warnings:
        count = len(result.warnings)
        typer.echo(f"Markdown validation passed with {count} warning(s).")
    else:
        typer.echo("Markdown validation passed.")
    return False


def _emit_registry_deltas(delta: RegistryDelta) -> None:
    for node in delta.missing_nodes:
        typer.echo(
            f"registry delta: missing node {node} (present in git)",
            err=True,
        )
    for node in delta.extra_nodes:
        typer.echo(
            f"registry delta: extra node {node} (not in git)",
            err=True,
        )
    for link in delta.missing_links:
        typer.echo(
            f"registry delta: missing link {link} (present in git)",
            err=True,
        )
    for link in delta.extra_links:
        typer.echo(
            f"registry delta: extra link {link} (not in git)",
            err=True,
        )
    if delta.has_differences:
        typer.echo(
            f"Registry differs from git ({delta.count} delta(s)). "
            "Run 'bellman sync' to update the registry.",
            err=True,
        )
    else:
        typer.echo("Registry matches git.")


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
            "Note: libfits not found; run sync after installing libfits.",
            err=True,
        )


create_app = typer.Typer(help="Create roadmap entities.")
app.add_typer(create_app, name="create")

report_app = typer.Typer(help="Export roadmap reports.")
app.add_typer(report_app, name="report")


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


class _WbsTyperGroup(TyperGroup):
    """Route ``report wbs PATH`` to the ``csv`` subcommand for compatibility."""

    def resolve_command(self, ctx, args):
        if "tree" not in args and "csv" not in args:
            path_index: int | None = None
            index = 0
            while index < len(args):
                arg = args[index]
                if arg in ("-o", "--output", "--project", "--path"):
                    index += 2
                    continue
                if arg.startswith("-"):
                    index += 1
                    continue
                if arg not in self.commands:
                    path_index = index
                    break
                index += 1
            if path_index is not None:
                args.insert(path_index, "csv")
        return super().resolve_command(ctx, args)


def _wbs_effective_options(
    ctx: typer.Context,
    *,
    path: Path | None,
    project: str | None,
    output: Path | None,
) -> tuple[Path | None, str | None, Path | None]:
    if not ctx.obj:
        return path, project, output
    return (
        path if path is not None else ctx.obj.get("path"),
        project if project is not None else ctx.obj.get("project"),
        output if output is not None else ctx.obj.get("output"),
    )


wbs_app = typer.Typer(
    help="Work-breakdown-structure reports.",
    cls=_WbsTyperGroup,
)
report_app.add_typer(wbs_app, name="wbs")


def _load_roadmap(path: Path | None) -> tuple[Path, Roadmap]:
    root = layout.roadmap_root(path)
    try:
        return root, load(root)
    except (ValueError, OSError) as exc:
        typer.echo(f"load error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _write_wbs_csv_report(
    path: Path | None,
    *,
    project: str | None,
    output: Path | None,
) -> None:
    root, roadmap = _load_roadmap(path)
    try:
        if output is None:
            write_wbs_csv(roadmap, sys.stdout, project_name=project)
            return

        out_path = output if output.is_absolute() else root / output
        write_wbs_csv_file(roadmap, out_path, project_name=project)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Wrote {out_path}")


def _write_wbs_tree_report(
    path: Path | None,
    *,
    project: str | None,
) -> None:
    _root_path, roadmap = _load_roadmap(path)
    try:
        write_wbs_tree(roadmap, sys.stdout, project_name=project)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@wbs_app.callback(invoke_without_command=True)
def report_wbs(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Roadmap root"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Export a single project by name"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output CSV file path (default: stdout)",
        ),
    ] = None,
) -> None:
    """Export a work-breakdown-structure CSV for roadmap work packages."""
    ctx.ensure_object(dict)
    ctx.obj["path"] = path
    ctx.obj["project"] = project
    ctx.obj["output"] = output
    if ctx.invoked_subcommand is not None:
        return

    _write_wbs_csv_report(path, project=project, output=output)


@wbs_app.command("csv")
def report_wbs_csv(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Export a single project by name"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output CSV file path (default: stdout)",
        ),
    ] = None,
) -> None:
    """Export a work-breakdown-structure CSV for roadmap work packages."""
    effective_path, effective_project, effective_output = _wbs_effective_options(
        ctx,
        path=path,
        project=project,
        output=output,
    )
    _write_wbs_csv_report(
        effective_path,
        project=effective_project,
        output=effective_output,
    )


@wbs_app.command("tree")
def report_wbs_tree(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Show a single project by name"),
    ] = None,
) -> None:
    """Print a work-package tree with PERT estimates to stdout."""
    effective_path, effective_project, _effective_output = _wbs_effective_options(
        ctx,
        path=path,
        project=project,
        output=None,
    )
    _write_wbs_tree_report(effective_path, project=effective_project)


@app.command()
def validate(
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
    registry: Annotated[
        bool,
        typer.Option(
            "--registry/--no-registry",
            help="Compare the pyfits registry to git markdown",
        ),
    ] = True,
) -> None:
    """Validate roadmap markdown and compare the registry to git."""
    root = _root(path)
    result, roadmap = _markdown_validation_result(root)
    markdown_failed = _emit_validation_result(result)

    if not registry:
        if markdown_failed:
            raise typer.Exit(code=1)
        return

    if not libfits_available():
        typer.echo(
            "Skipping registry delta check: libfits not available.",
            err=True,
        )
        if markdown_failed:
            raise typer.Exit(code=1)
        return

    delta_result = compute_registry_delta(root, roadmap)
    if isinstance(delta_result, Err):
        err = delta_result.err_value
        message = err.format() if isinstance(err, RegistryDeltaError) else str(err)
        typer.echo(f"Registry delta check failed: {message}", err=True)
        raise typer.Exit(code=1)
    _emit_registry_deltas(delta_result.ok_value)

    if markdown_failed:
        raise typer.Exit(code=1)


@app.command()
def sync(
    path: Annotated[
        Path | None,
        typer.Argument(help="Roadmap root directory (default: cwd)"),
    ] = None,
) -> None:
    """Sync git markdown into the pyfits registry after validation passes."""
    root = _root(path)
    result, _roadmap = _markdown_validation_result(root)
    if _emit_validation_result(result):
        raise typer.Exit(code=1)

    if not libfits_available():
        typer.echo("Graph sync failed: libfits not available.", err=True)
        raise typer.Exit(code=1)

    sync_result = sync_roadmap(root, prune=True)
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
