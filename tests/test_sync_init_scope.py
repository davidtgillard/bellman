"""Tests for init-only pyfits bootstrap and validate side-effects."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"
runner = CliRunner()


def test_sync_roadmap_requires_init(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with patch("bellman.graph.sync.libfits_available", return_value=True):
        result = sync_roadmap(tmp_path)
    assert isinstance(result, Err)
    assert result.err_value.code == "not_initialized"
    assert not (tmp_path / ".fits").exists()
    assert not (tmp_path / "nodes").exists()
    assert not (tmp_path / "links").exists()


@pytest.mark.integration
def test_init_pyfits_creates_fits_dir(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    result = init_pyfits_repo(tmp_path)
    assert isinstance(result, Ok)
    assert (tmp_path / ".fits").is_dir()


@pytest.mark.integration
def test_validate_from_subfolder_uses_parent_fits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    shutil.copytree(EXAMPLES, tmp_path / "roadmap")
    roadmap = tmp_path / "roadmap"
    subfolder = roadmap / "projects" / "billing-redesign"
    assert subfolder.is_dir()
    init_result = init_pyfits_repo(roadmap)
    assert isinstance(init_result, Ok)
    monkeypatch.chdir(subfolder)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert not (subfolder / ".fits").exists()
    assert (roadmap / ".fits").is_dir()


def test_validate_without_init_does_not_create_fits(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=True):
        result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "no initialized bellman roadmap" in result.output
    assert not (tmp_path / ".fits").exists()


@pytest.mark.integration
def test_init_creates_fits_at_specified_path(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".fits").is_dir()
    assert (tmp_path / "initiatives").is_dir()
