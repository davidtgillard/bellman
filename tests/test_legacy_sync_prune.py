"""Integration tests for legacy flat-id migration during sync prune."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyfits import Repo
from pyfits.result import Ok

from bellman import layout
from bellman.graph.desired import entity_node_id
from bellman.graph.identity import InstanceIndex
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap


def _write_registry_instances(root: Path, instances: list[dict[str, object]]) -> None:
    registry_path = root / ".fits" / "registry.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    data["instances"] = instances
    registry_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.mark.integration
def test_sync_prune_tolerates_legacy_registry_ghosts(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "manual-goal")
    assert isinstance(init_pyfits_repo(tmp_path), Ok)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    qualified = entity_node_id("goal", "manual-goal")
    index = InstanceIndex.load(tmp_path)
    assert isinstance(index, Ok)
    kind = index.ok_value.by_name["goal"]
    goal = index.ok_value.by_name[qualified]
    _write_registry_instances(
        tmp_path,
        [
            {
                "guid": kind.guid,
                "name": "goal",
                "type": "kind",
                "kind": "node",
                "scope": "root",
            },
            {
                "guid": goal.guid,
                "name": "manual-goal",
                "type": "goal",
                "kind": "node",
                "scope": "root",
            },
            {
                "guid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                "name": "goal--manual-goal",
                "type": "goal",
                "kind": "node",
                "scope": "root",
            },
        ],
    )

    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)

    open_result = Repo.open(tmp_path)
    assert isinstance(open_result, Ok)
    with open_result.ok_value as repo:
        validation = repo.validate(include_nested_subgraphs=True)
    index_after = InstanceIndex.load(tmp_path)
    assert isinstance(index_after, Ok)
    assert qualified in index_after.ok_value.live_node_names()
    assert isinstance(validation, Ok)


@pytest.mark.integration
def test_sync_removes_legacy_wp_registry_ghost(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "demo")
    wp_path = layout.work_packages_path(tmp_path, "demo")
    wp_path.write_text(
        """version: 1

work_packages:
  - title: First
    description: TBD.
""",
        encoding="utf-8",
    )
    assert isinstance(init_pyfits_repo(tmp_path), Ok)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    modern_wp = "project/demo/first"
    registry_path = tmp_path / ".fits" / "registry.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    data["instances"].append(
        {
            "guid": "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
            "name": "demo--first",
            "type": "work_package",
            "kind": "node",
            "scope": "root",
        }
    )
    registry_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)

    open_result = Repo.open(tmp_path)
    assert isinstance(open_result, Ok)
    with open_result.ok_value as repo:
        validation = repo.validate(include_nested_subgraphs=True)
    index_after = InstanceIndex.load(tmp_path)
    assert isinstance(index_after, Ok)
    assert modern_wp in index_after.ok_value.live_node_names()
    assert isinstance(validation, Ok)
