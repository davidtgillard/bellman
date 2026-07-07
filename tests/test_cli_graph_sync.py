"""CLI tests for post-mutation graph sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.errors import FitsError
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman.cli import app

runner = CliRunner()


def _write_fits_marker(root: Path) -> None:
    (root / ".fits").mkdir()


def test_create_initiative_calls_sync(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
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
            ["create", "initiative", "my-init", "--path", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert sync_calls == [False]
    assert "Graph sync passed." in result.output


def test_create_initiative_sync_failure_exits_1(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.sync_roadmap",
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
