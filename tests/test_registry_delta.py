"""Registry delta tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.models import Graph
from pyfits.result import Ok

from bellman import layout
from bellman.graph.delta import compute_registry_delta
from bellman.graph.desired import DesiredNode, desired_links, desired_nodes
from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex
from bellman.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_desired_nodes_include_milestones() -> None:
    roadmap = load(EXAMPLES)
    nodes = desired_nodes(roadmap)
    assert any(
        node.type_name == "milestone" and node.node_id == "milestone/ga-release"
        for node in nodes
    )


def test_desired_links_include_parent_of() -> None:
    roadmap = load(EXAMPLES)
    links = desired_links(roadmap)
    assert any(link.link_type == "parent_of" for link in links)


_OK_MILESTONE = """# Manual Milestone

## Date

2026-09-30

## Description

Added by hand.
"""


def test_compute_registry_delta_reports_missing_milestone(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / "milestones" / "manual-milestone.md").write_text(
        _OK_MILESTONE,
        encoding="utf-8",
    )
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(GraphHistory())),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=Graph(nodes=(), edges=()))),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)

    assert isinstance(result, Ok)
    delta = result.ok_value
    assert delta.missing_nodes == ("milestone manual-milestone",)
    assert delta.has_differences
    assert delta.missing_node_ids == frozenset(
        {DesiredNode("milestone", "milestone/manual-milestone")}
    )
    assert delta.desired_node_count == 1
    assert delta.actual_node_count == 0


def test_compute_registry_delta_reports_extra_milestone(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)

    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="00000000-0000-0000-0000-000000000001",
                instance_name="orphan-milestone",
                type_name="milestone",
                kind="node",
            ),
        )
    )
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(history)),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=Graph(nodes=(), edges=()))),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)

    assert isinstance(result, Ok)
    delta = result.ok_value
    assert delta.extra_nodes == ("milestone orphan-milestone",)
    assert delta.has_differences
    assert any(node.type_name == "milestone" for node in delta.extra_node_ids)
    assert delta.actual_node_count == 1
    assert delta.desired_node_count == 0


def test_compute_registry_delta_reports_obsolete_goal_graph(tmp_path: Path) -> None:
    from pyfits import Id
    from pyfits.models import GraphEdge

    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)
    kind_guid = "00000000-0000-0000-0000-000000000001"
    goal_guid = "00000000-0000-0000-0000-000000000002"
    milestone_root = "00000000-0000-0000-0000-000000000003"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=kind_guid,
                instance_name="goal",
                type_name="kind",
                kind="node",
            ),
            InstanceRecord(
                guid=goal_guid,
                instance_name="reduce-churn",
                type_name="goal",
                kind="node",
                parent_guid=kind_guid,
            ),
            InstanceRecord(
                guid=milestone_root,
                instance_name="milestone",
                type_name="kind",
                kind="node",
            ),
        )
    )
    graph = Graph(
        nodes=(),
        edges=(
            GraphEdge(
                from_id=Id(kind_guid),
                to_id=Id(goal_guid),
                kind="registered_link",
                link_type="supports",
                id=Id("00000000-0000-0000-0000-000000000004"),
            ),
            GraphEdge(
                from_id=Id(kind_guid),
                to_id=Id(goal_guid),
                kind="registered_link",
                link_type="supports_wp",
                id=Id("00000000-0000-0000-0000-000000000005"),
            ),
        ),
    )
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(history)),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=graph)),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)

    assert isinstance(result, Ok)
    delta = result.ok_value
    assert delta.extra_nodes == ("goal reduce-churn", "kind goal")
    assert delta.extra_links == (
        "supports goal/reduce-churn -> goal",
        "supports_wp goal/reduce-churn -> goal",
    )
    assert delta.has_differences
    assert delta.extra_node_ids == frozenset()
    assert "milestone" not in " ".join(delta.extra_nodes)


def test_compute_registry_delta_detects_legacy_id_migration(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / "milestones" / "manual-milestone.md").write_text(
        _OK_MILESTONE,
        encoding="utf-8",
    )
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="00000000-0000-0000-0000-000000000001",
                instance_name="manual-milestone",
                type_name="milestone",
                kind="node",
            ),
        )
    )
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(history)),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=Graph(nodes=(), edges=()))),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)

    assert isinstance(result, Ok)
    assert result.ok_value.needs_id_migration


def test_compute_registry_delta_no_differences_when_aligned(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)
    assert roadmap.milestones == ()

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(GraphHistory())),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=Graph(nodes=(), edges=()))),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)

    assert isinstance(result, Ok)
    assert not result.ok_value.has_differences


class _FakeRepo:
    def __init__(self, *, graph: Graph) -> None:
        self._graph = graph

    def __enter__(self) -> _FakeRepo:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def output_graph(self, *, include_nested: bool = False) -> Ok[Graph]:
        return Ok(self._graph)


def test_registry_delta_properties() -> None:
    from bellman.graph.delta import RegistryDelta

    empty = RegistryDelta((), (), (), ())
    assert not empty.has_differences
    assert empty.count == 0
    delta = RegistryDelta(("n",), ("e",), ("ml",), ("el",), needs_id_migration=True)
    assert delta.has_differences
    assert delta.count == 4


def test_registry_delta_error_format() -> None:
    from bellman.graph.delta import RegistryDeltaError

    assert RegistryDeltaError("x").format() == "x"


def test_compute_registry_delta_libfits_unavailable(tmp_path: Path) -> None:
    from pyfits.result import Err

    from bellman.graph.delta import RegistryDeltaError

    layout.ensure_roadmap_dirs(tmp_path)
    roadmap = load(tmp_path)
    with patch("bellman.graph.delta.libfits_available", return_value=False):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Err)
    assert isinstance(result.err_value, RegistryDeltaError)


def test_compute_registry_delta_no_fits_dir(tmp_path: Path) -> None:
    from pyfits.result import Err

    from bellman.graph.delta import RegistryDeltaError

    layout.ensure_roadmap_dirs(tmp_path)
    roadmap = load(tmp_path)
    with patch("bellman.graph.delta.libfits_available", return_value=True):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Err)
    assert isinstance(result.err_value, RegistryDeltaError)
    assert "not initialized" in result.err_value.message
