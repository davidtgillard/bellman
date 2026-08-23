"""Tests for targeted graph prune after entity deletion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pyfits.result import Err, Ok

from bellman import layout
from bellman.graph.desired import entity_node_id
from bellman.graph.identity import InstanceIndex
from bellman.graph.sync import (
    init_pyfits_repo,
    libfits_available,
    prune_deleted_entity,
    sync_created_entity,
    sync_roadmap,
)

_BROKEN_WORK_PACKAGES = """version: 1

work_packages:
  - title: UI Development
    description: TBD.
    dependencies:
      - lcc-development
"""


def _bootstrap_pyfits(root: Path) -> None:
    result = init_pyfits_repo(root)
    assert isinstance(result, Ok)


@pytest.mark.integration
def test_sync_roadmap_returns_err_on_load_failure(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "good-init")
    layout.create_project(tmp_path, "broken-project")
    wp_path = layout.work_packages_path(tmp_path, "broken-project")
    wp_path.write_text(_BROKEN_WORK_PACKAGES, encoding="utf-8")
    _bootstrap_pyfits(tmp_path)

    result = sync_roadmap(tmp_path)

    assert isinstance(result, Err)
    assert result.err_value.code == "roadmap_load_failed"
    assert "invalid dependency syntax" in str(result.err_value).lower()


@pytest.mark.integration
def test_prune_deleted_entity_with_unrelated_load_error(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "legacy-image-closeout")
    layout.create_project(tmp_path, "broken-project")
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    wp_path = layout.work_packages_path(tmp_path, "broken-project")
    wp_path.write_text(_BROKEN_WORK_PACKAGES, encoding="utf-8")
    assert isinstance(sync_roadmap(tmp_path), Err)

    layout.delete_entity(tmp_path, "legacy-image-closeout")
    result = prune_deleted_entity(tmp_path, "initiative", "legacy-image-closeout")

    assert isinstance(result, Ok)
    assert not (tmp_path / "initiatives" / "legacy-image-closeout.md").exists()


def test_cli_delete_succeeds_with_unrelated_parse_error(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    from typer.testing import CliRunner

    from bellman.cli import app

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "legacy-image-closeout")
    layout.create_project(tmp_path, "broken-project")
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    wp_path = layout.work_packages_path(tmp_path, "broken-project")
    wp_path.write_text(_BROKEN_WORK_PACKAGES, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["delete", "legacy-image-closeout", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Deleted initiatives/legacy-image-closeout.md" in result.output
    assert "Graph sync passed." in result.output
    assert not (tmp_path / "initiatives" / "legacy-image-closeout.md").exists()


@pytest.mark.integration
def test_sync_created_entity_with_unrelated_load_error(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "broken-project")
    wp_path = layout.work_packages_path(tmp_path, "broken-project")
    wp_path.write_text(_BROKEN_WORK_PACKAGES, encoding="utf-8")
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Err)

    layout.create_initiative(tmp_path, "kri-image-tools")
    result = sync_created_entity(tmp_path, "initiative", "kri-image-tools")

    assert isinstance(result, Ok)


def test_cli_create_initiative_with_unrelated_parse_error(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    from typer.testing import CliRunner

    from bellman.cli import app

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "broken-project")
    wp_path = layout.work_packages_path(tmp_path, "broken-project")
    wp_path.write_text(_BROKEN_WORK_PACKAGES, encoding="utf-8")
    _bootstrap_pyfits(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["create", "initiative", "kri-image-tools", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Created" in result.output
    assert "kri-image-tools" in result.output
    assert "Graph sync passed." in result.output
    assert (tmp_path / "initiatives" / "kri-image-tools.md").is_file()


def _has_live_logical(root: Path, logical_name: str) -> bool:
    result = InstanceIndex.load(root)
    if isinstance(result, Err):
        return False
    return logical_name in result.ok_value.live_node_names()


@pytest.mark.integration
def test_prune_deleted_project_with_work_packages(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "demo-project")
    wp_path = layout.work_packages_path(tmp_path, "demo-project")
    wp_path.write_text(
        """version: 1

work_packages:
  - title: First
    description: TBD.
  - title: Second
    description: TBD.
""",
        encoding="utf-8",
    )
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _has_live_logical(tmp_path, "project/demo-project/first")
    assert _has_live_logical(tmp_path, "project/demo-project/second")

    layout.delete_entity(tmp_path, "demo-project")
    result = prune_deleted_entity(tmp_path, "project", "demo-project")
    assert isinstance(result, Ok)
    assert not _has_live_logical(tmp_path, entity_node_id("project", "demo-project"))
    assert not _has_live_logical(tmp_path, "project/demo-project/first")
    assert not _has_live_logical(tmp_path, "project/demo-project/second")


def test_prune_deleted_entity_unknown_kind(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    with patch("bellman.graph.sync.libfits_available", return_value=True):
        result = prune_deleted_entity(tmp_path, "bogus", "x")
    assert isinstance(result, Err)
    assert result.err_value.code == "invalid_entity"


def test_prune_deleted_entity_libfits_unavailable(tmp_path: Path) -> None:
    with patch("bellman.graph.sync.libfits_available", return_value=False):
        result = prune_deleted_entity(tmp_path, "goal", "x")
    assert isinstance(result, Err)
    assert result.err_value.code == "lib_not_found"
