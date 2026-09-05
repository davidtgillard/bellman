"""E2E round-trip tests for promote/demote filesystem identity."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.result import Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app

runner = CliRunner()

_WP_YAML = """version: 1

work_packages:
  - title: wp-invoicing
    description: Core invoicing flow.
    estimate: [1d, 2d, 3d]
"""


def _write_fits_marker(root: Path) -> None:
    (root / ".fits").mkdir()


def _tree_snapshot(path: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for child in sorted(path.rglob("*")):
        if child.is_file():
            files[str(child.relative_to(path))] = child.read_text(encoding="utf-8")
    return files


def test_cli_promote_demote_promote_round_trip(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "round-trip")
    initiative_v1 = layout.initiative_path(tmp_path, "round-trip").read_text(
        encoding="utf-8"
    )

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_roadmap", return_value=Ok(None)),
    ):
        promoted = runner.invoke(
            app,
            ["promote", "round-trip", "--path", str(tmp_path)],
        )
        assert promoted.exit_code == 0

        project_dir = layout.project_dir(tmp_path, "round-trip")
        layout.work_packages_path(tmp_path, "round-trip").write_text(
            _WP_YAML,
            encoding="utf-8",
        )
        (project_dir / "notes.txt").write_text("sidecar\n", encoding="utf-8")
        project_v1 = _tree_snapshot(project_dir)

        demoted = runner.invoke(
            app,
            ["demote", "round-trip", "--path", str(tmp_path)],
        )
        assert demoted.exit_code == 0
        initiative_v2 = layout.initiative_path(tmp_path, "round-trip").read_text(
            encoding="utf-8"
        )
        assert initiative_v2 == initiative_v1
        assert not project_dir.exists()
        stash = layout.archived_project_dir(tmp_path, "round-trip")
        assert stash.is_dir()
        assert (stash / "notes.txt").read_text(encoding="utf-8") == "sidecar\n"
        assert "wp-invoicing" in (stash / "work-packages.yaml").read_text(
            encoding="utf-8"
        )

        repromoted = runner.invoke(
            app,
            ["promote", "round-trip", "--path", str(tmp_path)],
        )
        assert repromoted.exit_code == 0
        project_v2 = _tree_snapshot(project_dir)
        assert project_v2 == project_v1
        assert not stash.exists()
