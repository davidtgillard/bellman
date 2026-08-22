"""Integration tests for pruning stale markdown-derived dependency links."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyfits import Repo
from pyfits.result import Ok

from bellman import layout
from bellman.graph.delta import compute_registry_delta
from bellman.graph.desired import (
    DesiredLink,
    desired_link_from_graph_edge,
    entity_node_id,
)
from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap
from bellman.roadmap import load

_SCOPE_LINK = DesiredLink(
    "precedes_FS_Mandatory_scope",
    "initiative/target-init",
    "initiative/dep-init",
)


def _bootstrap_pyfits(root: Path) -> None:
    result = init_pyfits_repo(root)
    assert isinstance(result, Ok)


def _add_scope_dependency(root: Path, *, dep: str, target: str) -> None:
    dep_path = layout.initiative_path(root, dep)
    dep_path.write_text(
        dep_path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            f"## Dependencies\n\n- {target} [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )


def _remove_scope_dependencies(root: Path, *, dep: str) -> None:
    dep_path = layout.initiative_path(root, dep)
    dep_path.write_text(
        dep_path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n- target-init [FS, Mandatory]\n",
            "## Dependencies\n\n",
        ),
        encoding="utf-8",
    )


def _has_live_nodes(root: Path, *logical_names: str) -> bool:
    index = InstanceIndex.load(root)
    if not isinstance(index, Ok):
        return False
    live = index.ok_value.live_node_names()
    return all(name in live for name in logical_names)


def _graph_has_desired_link(root: Path, link: DesiredLink) -> bool:
    open_result = Repo.open(root)
    if not isinstance(open_result, Ok):
        return False
    with open_result.ok_value as repo:
        graph_result = repo.output_graph(include_nested=True)
    if not isinstance(graph_result, Ok):
        return False
    index = InstanceIndex.load(root)
    if not isinstance(index, Ok):
        return False
    for edge in graph_result.ok_value.edges:
        desired = desired_link_from_graph_edge(
            link_type=edge.link_type,
            from_id_value=edge.from_id.value,
            to_id_value=edge.to_id.value,
            index=index.ok_value,
        )
        if desired == link:
            return True
    return False


def test_desired_link_from_graph_edge_maps_out_to_in() -> None:
    pred_guid = "00000000-0000-0000-0000-000000000001"
    succ_guid = "00000000-0000-0000-0000-000000000002"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=pred_guid,
                instance_name="target-init",
                type_name="initiative",
                kind="node",
            ),
            InstanceRecord(
                guid=succ_guid,
                instance_name="dep-init",
                type_name="initiative",
                kind="node",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    desired = desired_link_from_graph_edge(
        link_type="precedes_FS_Mandatory_scope",
        from_id_value=succ_guid,
        to_id_value=pred_guid,
        index=index,
    )
    assert desired == DesiredLink(
        "precedes_FS_Mandatory_scope",
        "target-init",
        "dep-init",
    )


@pytest.mark.integration
def test_sync_prune_removes_stale_scope_dependency(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "dep-init")
    layout.create_initiative(tmp_path, "target-init")
    _add_scope_dependency(tmp_path, dep="dep-init", target="target-init")
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _graph_has_desired_link(tmp_path, _SCOPE_LINK)

    _remove_scope_dependencies(tmp_path, dep="dep-init")
    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)
    assert _has_live_nodes(
        tmp_path,
        entity_node_id("initiative", "dep-init"),
        entity_node_id("initiative", "target-init"),
    )
    assert not _graph_has_desired_link(tmp_path, _SCOPE_LINK)

    delta = compute_registry_delta(tmp_path, load(tmp_path))
    assert isinstance(delta, Ok)
    assert _SCOPE_LINK.link_type not in "".join(delta.ok_value.extra_links)


@pytest.mark.integration
def test_sync_adds_scope_dependency_link(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "dep-init")
    layout.create_initiative(tmp_path, "target-init")
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert not _graph_has_desired_link(tmp_path, _SCOPE_LINK)

    _add_scope_dependency(tmp_path, dep="dep-init", target="target-init")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _graph_has_desired_link(tmp_path, _SCOPE_LINK)


@pytest.mark.integration
def test_sync_prune_removes_stale_wp_dependency(tmp_path: Path) -> None:
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
    dependencies:
      - predecessor: first
""",
        encoding="utf-8",
    )
    wp_link = DesiredLink(
        "precedes_FS_Mandatory",
        "project/demo-project/first",
        "project/demo-project/second",
    )
    _bootstrap_pyfits(tmp_path)
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _graph_has_desired_link(tmp_path, wp_link)

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
    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)
    assert _has_live_nodes(
        tmp_path,
        "project/demo-project/first",
        "project/demo-project/second",
    )
    assert not _graph_has_desired_link(tmp_path, wp_link)
