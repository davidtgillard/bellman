"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import semver
from pyfits.errors import FitsError
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app
from bellman.graph.delta import RegistryDelta

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert semver.Version.parse(result.stdout.strip())


def test_init_and_create(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    result = runner.invoke(
        app,
        ["create", "initiative", "my-init", "--path", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert (tmp_path / "initiatives" / "my-init.md").is_file()


def test_create_project_milestone_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch("bellman.cli.libfits_available", return_value=False):
        for kind, name in (
            ("project", "demo-proj"),
            ("milestone", "m1"),
            ("goal", "g1"),
        ):
            result = runner.invoke(
                app,
                ["create", kind, name, "--path", str(tmp_path)],
            )
            assert result.exit_code == 0, result.output
            assert "Created" in result.output
    assert layout.project_dir(tmp_path, "demo-proj").is_dir()
    assert layout.milestone_path(tmp_path, "m1").is_file()
    assert layout.goal_path(tmp_path, "g1").is_file()


def test_create_duplicate_exits_1(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    layout.create_initiative(tmp_path, "dup-init")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["create", "initiative", "dup-init", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_init_without_libfits(tmp_path: Path) -> None:
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert "Initialized roadmap" in result.output
    assert "libfits not found" in result.output
    assert (tmp_path / "initiatives").is_dir()


def test_init_warns_when_init_pyfits_fails(tmp_path: Path) -> None:
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.init_pyfits_repo",
            return_value=Err(FitsError("init boom", code="test")),
        ),
        patch("bellman.cli.sync_roadmap") as sync_mock,
    ):
        result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert "Warning: graph bootstrap failed" in result.output
    assert "init boom" in result.output
    sync_mock.assert_not_called()


def test_init_warns_when_sync_roadmap_fails(tmp_path: Path) -> None:
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.init_pyfits_repo", return_value=Ok(None)),
        patch(
            "bellman.cli.sync_roadmap",
            return_value=Err(FitsError("sync boom", code="test")),
        ),
    ):
        result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert "Warning: graph bootstrap failed" in result.output
    assert "sync boom" in result.output


def test_report_deps_cli() -> None:
    result = runner.invoke(app, ["report", "deps", "--path", str(EXAMPLES)])
    assert result.exit_code == 0
    assert "->" in result.stdout


def test_report_dependencies_cli_alias() -> None:
    result = runner.invoke(
        app,
        ["report", "dependencies", "--path", str(EXAMPLES)],
    )
    assert result.exit_code == 0
    assert "->" in result.stdout


def test_report_wbs_csv_subcommand() -> None:
    result = runner.invoke(app, ["report", "wbs", "csv", str(EXAMPLES)])
    assert result.exit_code == 0
    assert "work package" in result.stdout


def test_create_without_roadmap_root(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(
        app,
        ["create", "goal", "g", "--path", str(empty)],
    )
    assert result.exit_code == 1
    assert "no initialized bellman roadmap" in result.output


def test_create_project_duplicate(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    layout.create_project(tmp_path, "dup-proj")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["create", "project", "dup-proj", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_create_milestone_and_goal_duplicate(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    layout.create_milestone(tmp_path, "dup-ms")
    layout.create_goal(tmp_path, "dup-goal")
    with patch("bellman.cli.libfits_available", return_value=False):
        for kind, name in (("milestone", "dup-ms"), ("goal", "dup-goal")):
            result = runner.invoke(
                app,
                ["create", kind, name, "--path", str(tmp_path)],
            )
            assert result.exit_code == 1
            assert "already exists" in result.output


def test_report_wbs_csv_writes_relative_output(tmp_path: Path) -> None:
    import shutil

    roadmap = tmp_path / "roadmap"
    shutil.copytree(EXAMPLES, roadmap, dirs_exist_ok=True)
    result = runner.invoke(
        app,
        ["report", "wbs", "csv", "-o", "out.csv", str(roadmap)],
    )
    assert result.exit_code == 0
    assert (roadmap / "out.csv").is_file()
    assert "Wrote" in result.output


def test_report_wbs_load_error(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    goals = tmp_path / "goals"
    goals.mkdir()
    (goals / "bad.md").write_text("no header\n", encoding="utf-8")
    result = runner.invoke(app, ["report", "wbs", "csv", str(tmp_path)])
    assert result.exit_code == 1
    assert "load error" in result.output


def test_validate_markdown_failed_with_registry(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    goals = tmp_path / "goals"
    goals.mkdir()
    (goals / "bad.md").write_text("# Wrong\n\nBody.\n", encoding="utf-8")
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.compute_registry_delta",
            return_value=Ok(RegistryDelta((), (), (), ())),
        ),
    ):
        result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1


def test_validate_markdown_failed_without_libfits(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    goals = tmp_path / "goals"
    goals.mkdir()
    (goals / "bad.md").write_text("# Wrong\n\nBody.\n", encoding="utf-8")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "Skipping registry delta" in result.output


def test_report_wbs_tree_value_error() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            "tree",
            "--project",
            "missing-project",
            str(EXAMPLES),
        ],
    )
    assert result.exit_code == 1
    assert "no project named" in result.output


def test_report_wbs_csv_unknown_project() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            "csv",
            "--project",
            "missing-project",
            str(EXAMPLES),
        ],
    )
    assert result.exit_code == 1
    assert "no project named" in result.output


def test_rename_positionals_skips_flags() -> None:
    from bellman.cli import _rename_positionals

    assert _rename_positionals(["--path", "/tmp", "old", "new"]) == ["old", "new"]
    assert _rename_positionals(["-v", "old", "new"]) == ["old", "new"]


def test_wbs_effective_options_without_ctx_obj() -> None:
    from types import SimpleNamespace
    from typing import cast

    import typer

    from bellman.cli import _wbs_effective_options

    ctx = cast(typer.Context, SimpleNamespace(obj=None))
    assert _wbs_effective_options(
        ctx, path=Path("."), project="p", output=Path("o")
    ) == (Path("."), "p", Path("o"))
