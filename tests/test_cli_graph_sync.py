"""CLI tests for post-mutation graph sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.errors import FitsError
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app

runner = CliRunner()


def _write_fits_marker(root: Path) -> None:
    (root / ".fits").mkdir()


def test_create_initiative_calls_sync(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    sync_calls: list[tuple[str, str]] = []

    def fake_sync(root: Path, kind: str, name: str) -> Ok[None]:
        sync_calls.append((kind, name))
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_created_entity", side_effect=fake_sync),
    ):
        result = runner.invoke(
            app,
            ["create", "initiative", "my-init", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert sync_calls == [("initiative", "my-init")]
    assert "Graph sync passed." in result.output


def test_create_initiative_sync_failure_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.sync_created_entity",
            return_value=Err(FitsError("boom", code="test")),
        ),
    ):
        result = runner.invoke(
            app,
            ["create", "initiative", "my-init", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert (tmp_path / "initiatives" / "my-init.md").is_file()
    assert "Graph sync failed" in result.output
    assert "code=test" in result.output


def test_create_project_milestone_goal_calls_sync(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    sync_calls: list[tuple[str, str]] = []

    def fake_sync(root: Path, kind: str, name: str) -> Ok[None]:
        sync_calls.append((kind, name))
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_created_entity", side_effect=fake_sync),
    ):
        for kind, name in (
            ("project", "p-one"),
            ("milestone", "m-one"),
            ("goal", "g-one"),
        ):
            result = runner.invoke(
                app,
                ["create", kind, name, "--path", str(tmp_path)],
            )
            assert result.exit_code == 0, result.output
    assert sync_calls == [
        ("project", "p-one"),
        ("milestone", "m-one"),
        ("goal", "g-one"),
    ]


def test_delete_calls_prune_deleted_entity(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout_dir = tmp_path / "goals"
    layout_dir.mkdir(parents=True)
    (layout_dir / "my-goal.md").write_text("# My Goal\n\nTBD.\n", encoding="utf-8")
    prune_calls: list[tuple[str, str]] = []

    def fake_prune(root: Path, kind: str, name: str) -> Ok[None]:
        prune_calls.append((kind, name))
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.prune_deleted_entity", side_effect=fake_prune),
    ):
        result = runner.invoke(
            app,
            ["delete", "my-goal", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert prune_calls == [("goal", "my-goal")]


def test_delete_missing_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    result = runner.invoke(
        app,
        ["delete", "no-such-entity", "--path", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "no entity named" in result.output


def test_delete_prune_failure_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "doomed")
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.prune_deleted_entity",
            return_value=Err(FitsError("prune boom", code="test")),
        ),
    ):
        result = runner.invoke(
            app,
            ["delete", "doomed", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert "Graph sync failed" in result.output


def test_delete_without_libfits_notes(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "note-goal")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["delete", "note-goal", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert "libfits not found" in result.output


def test_create_without_libfits_skips_sync(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["create", "initiative", "my-init", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert "libfits not found" in result.output
    assert "Graph sync passed." not in result.output


def test_promote_success_calls_sync(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "to-promote")
    sync_calls: list[bool] = []

    def fake_sync(root: Path, *, prune: bool = False) -> Ok[None]:
        sync_calls.append(prune)
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_roadmap", side_effect=fake_sync),
    ):
        result = runner.invoke(
            app,
            ["promote", "to-promote", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert "Promoted to" in result.output
    assert layout.project_dir(tmp_path, "to-promote").is_dir()
    assert sync_calls == [False]
    assert "Graph sync passed." in result.output


def test_promote_missing_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    result = runner.invoke(
        app,
        ["promote", "missing-init", "--path", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


def test_promote_sync_failure_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "promo-fail")
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.sync_roadmap",
            return_value=Err(FitsError("promo boom", code="test")),
        ),
    ):
        result = runner.invoke(
            app,
            ["promote", "promo-fail", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert "Graph sync failed" in result.output


def test_promote_without_libfits_notes(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "promo-note")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["promote", "promo-note", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert "libfits not found" in result.output


def test_rename_bare_calls_sync_renamed_entity(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout_dir = tmp_path / "goals"
    layout_dir.mkdir(parents=True)
    (layout_dir / "old-goal.md").write_text("# Old Goal\n\nTBD.\n", encoding="utf-8")
    sync_calls: list[tuple[str, str, str]] = []

    def fake_sync(root: Path, kind: str, old_name: str, new_name: str) -> Ok[None]:
        sync_calls.append((kind, old_name, new_name))
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_renamed_entity", side_effect=fake_sync),
    ):
        result = runner.invoke(
            app,
            ["rename", "old-goal", "new-goal", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert sync_calls == [("goal", "old-goal", "new-goal")]
    assert (layout_dir / "new-goal.md").is_file()
    assert "Graph sync passed." in result.output


def test_rename_typed_goal(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["rename", "goal", "system-mci", "renamed-goal", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert layout.goal_path(tmp_path, "renamed-goal").is_file()
    assert layout.initiative_path(tmp_path, "system-mci").is_file()


def test_rename_initiative_project_milestone(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "old-init")
    layout.create_project(tmp_path, "old-proj")
    layout.create_milestone(tmp_path, "old-ms")
    with patch("bellman.cli.libfits_available", return_value=False):
        for kind, old, new in (
            ("initiative", "old-init", "new-init"),
            ("project", "old-proj", "new-proj"),
            ("milestone", "old-ms", "new-ms"),
        ):
            result = runner.invoke(
                app,
                ["rename", kind, old, new, "--path", str(tmp_path)],
            )
            assert result.exit_code == 0, result.output
            assert "Renamed" in result.output
    assert layout.initiative_path(tmp_path, "new-init").is_file()
    assert layout.project_dir(tmp_path, "new-proj").is_dir()
    assert layout.milestone_path(tmp_path, "new-ms").is_file()


def test_rename_value_error_invalid_kebab(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "valid-goal")
    result = runner.invoke(
        app,
        ["rename", "goal", "valid-goal", "Not_Valid", "--path", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "kebab-case" in result.output


def test_rename_sync_failure_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "rename-fail")
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.sync_renamed_entity",
            return_value=Err(FitsError("rename boom", code="test")),
        ),
    ):
        result = runner.invoke(
            app,
            ["rename", "goal", "rename-fail", "renamed-ok", "--path", str(tmp_path)],
        )
    assert result.exit_code == 1
    assert "Graph sync failed" in result.output


def test_rename_ambiguous_shows_hint(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    result = runner.invoke(
        app,
        ["rename", "system-mci", "renamed", "--path", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "ambiguous name" in result.output
    assert "bellman rename <kind>" in result.output
