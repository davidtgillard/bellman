"""CLI tests for validate deltas and sync command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.errors import FitsError
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman.cli import app
from bellman.graph.delta import RegistryDelta

runner = CliRunner()


def _write_fits_marker(root: Path) -> None:
    (root / ".fits").mkdir()


def test_validate_reports_all_load_errors(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    goals = tmp_path / "goals"
    goals.mkdir(parents=True)
    (goals / "bad-a.md").write_text("no header\n", encoding="utf-8")
    (goals / "bad-b.md").write_text("also no header\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", "--no-registry", str(tmp_path)])
    assert result.exit_code == 1
    assert "bad-a.md" in result.output
    assert "bad-b.md" in result.output


def test_validate_reports_all_validation_errors(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    goals = tmp_path / "goals"
    goals.mkdir(parents=True)
    (goals / "bad-one.md").write_text("# Wrong One\n\nContent.\n", encoding="utf-8")
    (goals / "bad-two.md").write_text("# Wrong Two\n\nContent.\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", "--no-registry", str(tmp_path)])
    assert result.exit_code == 1
    assert result.output.count("does not match name") == 2


def test_validate_does_not_sync(tmp_path: Path) -> None:
    from bellman import layout

    layout.ensure_roadmap_dirs(tmp_path)
    _write_fits_marker(tmp_path)
    with (
        patch("bellman.cli.sync_roadmap") as sync_mock,
        patch("bellman.cli.libfits_available", return_value=False),
    ):
        result = runner.invoke(app, ["validate", str(tmp_path)])
    sync_mock.assert_not_called()
    assert result.exit_code == 0


def test_validate_no_registry_skips_registry_check(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with patch("bellman.cli.compute_registry_delta") as delta_mock:
        result = runner.invoke(app, ["validate", "--no-registry", str(tmp_path)])
    delta_mock.assert_not_called()
    assert result.exit_code == 0
    assert "Registry matches git." not in result.output


def test_validate_reports_registry_deltas(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    delta = RegistryDelta(
        missing_nodes=("goal manual-goal",),
        extra_nodes=(),
        missing_links=(),
        extra_links=(),
    )
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.compute_registry_delta", return_value=Ok(delta)),
    ):
        result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0
    assert "registry delta: missing node goal manual-goal" in result.output
    assert "bellman sync" in result.output


def test_sync_requires_markdown_validation_pass(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    goals = tmp_path / "goals"
    goals.mkdir(parents=True)
    (goals / "bad-goal.md").write_text("# Wrong Title\n\nContent.\n", encoding="utf-8")
    with patch("bellman.cli.sync_roadmap") as sync_mock:
        result = runner.invoke(app, ["sync", str(tmp_path)])
    sync_mock.assert_not_called()
    assert result.exit_code == 1


def test_sync_runs_after_validation(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    sync_calls: list[bool] = []

    def fake_sync(root: Path, *, prune: bool = False) -> Ok[None]:
        sync_calls.append(prune)
        return Ok(None)

    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch("bellman.cli.sync_roadmap", side_effect=fake_sync),
    ):
        result = runner.invoke(app, ["sync", str(tmp_path)])
    assert result.exit_code == 0
    assert sync_calls == [True]
    assert "Graph sync and libfits validation passed." in result.output


def test_sync_fails_when_libfits_unavailable(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(app, ["sync", str(tmp_path)])
    assert result.exit_code == 1
    assert "libfits not available" in result.output


def test_sync_reports_sync_failure(tmp_path: Path) -> None:
    _write_fits_marker(tmp_path)
    with (
        patch("bellman.cli.libfits_available", return_value=True),
        patch(
            "bellman.cli.sync_roadmap",
            return_value=Err(FitsError("boom", code="test")),
        ),
    ):
        result = runner.invoke(app, ["sync", str(tmp_path)])
    assert result.exit_code == 1
    assert "Graph sync failed" in result.output
