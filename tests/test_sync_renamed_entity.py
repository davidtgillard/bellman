"""Integration tests for sync_renamed_entity and sync_created_entity."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyfits.result import Err, Ok

from bellman import layout
from bellman.graph.desired import entity_node_id
from bellman.graph.identity import InstanceIndex
from bellman.graph.sync import (
    init_pyfits_repo,
    libfits_available,
    sync_created_entity,
    sync_renamed_entity,
    sync_roadmap,
)


def _bootstrap_pyfits(root: Path) -> None:
    result = init_pyfits_repo(root)
    assert isinstance(result, Ok)


def _has_live_logical(root: Path, logical_name: str) -> bool:
    result = InstanceIndex.load(root)
    if isinstance(result, Err):
        return False
    return logical_name in result.ok_value.live_node_names()


def _add_initiative_dependency(root: Path, *, dep: str, target: str) -> None:
    dep_path = layout.initiative_path(root, dep)
    dep_path.write_text(
        dep_path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            f"## Dependencies\n\n- {target} [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_sync_renamed_goal(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_goal(tmp_path, "old-goal")
    assert isinstance(sync_created_entity(tmp_path, "goal", "old-goal"), Ok)
    assert _has_live_logical(tmp_path, entity_node_id("goal", "old-goal"))

    layout.rename_entity(tmp_path, "old-goal", "new-goal", kind="goal")
    result = sync_renamed_entity(tmp_path, "goal", "old-goal", "new-goal")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("goal", "new-goal"))
    assert not _has_live_logical(tmp_path, entity_node_id("goal", "old-goal"))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("kind", "create_fn", "old_name", "new_name"),
    [
        ("initiative", layout.create_initiative, "old-init", "new-init"),
        ("project", layout.create_project, "old-proj", "new-proj"),
        ("milestone", layout.create_milestone, "old-mile", "new-mile"),
    ],
)
def test_sync_renamed_entity_kinds(
    tmp_path: Path,
    kind: str,
    create_fn: object,
    old_name: str,
    new_name: str,
) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    create_fn(tmp_path, old_name)  # type: ignore[operator]
    assert isinstance(sync_created_entity(tmp_path, kind, old_name), Ok)
    assert _has_live_logical(tmp_path, entity_node_id(kind, old_name))

    layout.rename_entity(tmp_path, old_name, new_name, kind=kind)
    result = sync_renamed_entity(tmp_path, kind, old_name, new_name)
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id(kind, new_name))
    assert not _has_live_logical(tmp_path, entity_node_id(kind, old_name))


@pytest.mark.integration
def test_sync_created_project_with_work_packages(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
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
    result = sync_created_entity(tmp_path, "project", "demo-project")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("project", "demo-project"))
    assert _has_live_logical(tmp_path, "project/demo-project/first")
    assert _has_live_logical(tmp_path, "project/demo-project/second")


@pytest.mark.integration
def test_sync_created_milestone(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_milestone(tmp_path, "ship-it")
    result = sync_created_entity(tmp_path, "milestone", "ship-it")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("milestone", "ship-it"))


@pytest.mark.integration
def test_sync_created_goal(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_goal(tmp_path, "reduce-churn")
    result = sync_created_entity(tmp_path, "goal", "reduce-churn")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("goal", "reduce-churn"))


@pytest.mark.integration
def test_sync_created_initiative_with_dependency(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_initiative(tmp_path, "target-init")
    assert isinstance(sync_created_entity(tmp_path, "initiative", "target-init"), Ok)
    layout.create_initiative(tmp_path, "dep-init")
    _add_initiative_dependency(tmp_path, dep="dep-init", target="target-init")
    result = sync_created_entity(tmp_path, "initiative", "dep-init")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("initiative", "dep-init"))
    assert _has_live_logical(tmp_path, entity_node_id("initiative", "target-init"))


def test_sync_renamed_entity_unknown_kind_unit(tmp_path: Path) -> None:
    result = sync_renamed_entity(tmp_path, "bogus", "a", "b")
    assert isinstance(result, Err)
    assert result.err_value.code == "invalid_entity"


def test_sync_created_entity_unknown_kind_unit(tmp_path: Path) -> None:
    result = sync_created_entity(tmp_path, "bogus", "x")
    assert isinstance(result, Err)
    assert result.err_value.code == "invalid_entity"


@pytest.mark.integration
def test_sync_renamed_after_full_roadmap(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_goal(tmp_path, "roadmap-goal")
    assert isinstance(sync_roadmap(tmp_path), Ok)
    layout.rename_entity(tmp_path, "roadmap-goal", "renamed-goal", kind="goal")
    result = sync_renamed_entity(tmp_path, "goal", "roadmap-goal", "renamed-goal")
    assert isinstance(result, Ok)
    assert _has_live_logical(tmp_path, entity_node_id("goal", "renamed-goal"))
