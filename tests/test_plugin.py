"""CLI and loader tests for repo-local plugins."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from snark.cli import app
from snark.plugin.loader import load_plugin_or_raise

runner = CliRunner()


def _write_echo_plugin(root: Path) -> None:
    plugin_dir = root / "plugin" / "echo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from snark.plugin import (
                FlagSpec,
                PluginArgumentSpecs,
                SnarkContext,
                SnarkPlugin,
                PluginArguments,
                TextIO,
            )

            def _run(ctx: SnarkContext, args: PluginArguments, io: TextIO) -> int:
                io.writeline("echo")
                if args.verbose:
                    io.writeline(ctx.snark_version)
                renames = ctx.history().renames
                io.writeline(f"renames:{len(renames)}")
                return 0

            PLUGIN = SnarkPlugin(
                name="echo",
                summary="Echo test plugin",
                args=PluginArgumentSpecs([FlagSpec("--verbose", help="Show version")]),
                run=_run,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_registry(root: Path) -> None:
    fits = root / ".fits"
    fits.mkdir(parents=True)
    (fits / "registry.json").write_text(
        json.dumps(
            {
                "description": "test",
                "version": 1,
                "kind": "fits-registry",
                "node_types": [],
                "link_types": [],
                "instance_renames": [],
            }
        ),
        encoding="utf-8",
    )


def test_plugin_list_and_run(tmp_path: Path) -> None:
    layout_dirs = ["initiatives", "projects", "milestones", "goals"]
    for name in layout_dirs:
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    _write_echo_plugin(tmp_path)

    result = runner.invoke(app, ["plugin", "--path", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "echo" in result.output
    assert "Echo test plugin" in result.output

    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "echo"],
    )
    assert result.exit_code == 0
    assert "echo" in result.output
    assert "renames:0" in result.output

    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "echo", "--verbose"],
    )
    assert result.exit_code == 0
    assert "echo" in result.output


def test_plugin_unknown_name(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    (tmp_path / "plugin").mkdir()
    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "missing"],
    )
    assert result.exit_code == 1
    assert "unknown plugin" in result.output


def test_load_plugin_name_mismatch(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin" / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from snark.plugin import (
                PluginArgumentSpecs,
                SnarkPlugin,
                SnarkContext,
                PluginArguments,
                TextIO,
            )

            def _run(ctx, args, io):
                return 0

            PLUGIN = SnarkPlugin(
                name="other",
                summary="x",
                args=PluginArgumentSpecs.empty(),
                run=_run,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    from snark.plugin.loader import PluginLoadError

    with pytest.raises(PluginLoadError, match="does not match"):
        load_plugin_or_raise(tmp_path, "bad")
