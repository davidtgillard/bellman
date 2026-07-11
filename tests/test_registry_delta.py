"""Registry delta tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.models import Graph
from pyfits.result import Ok

from bellman import layout
from bellman.graph.delta import compute_registry_delta
from bellman.graph.desired import desired_links, desired_nodes
from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex
from bellman.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_desired_nodes_include_goals() -> None:
    roadmap = load(EXAMPLES)
    nodes = desired_nodes(roadmap)
    assert any(
        node.type_name == "goal" and node.node_id == "goal--reduce-churn"
        for node in nodes
    )


def test_desired_links_include_parent_of() -> None:
    roadmap = load(EXAMPLES)
    links = desired_links(roadmap)
    assert any(link.link_type == "parent_of" for link in links)


def test_compute_registry_delta_reports_missing_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / "goals" / "manual-goal.md").write_text(
        "# Manual Goal\n\nAdded by hand.\n",
        encoding="utf-8",
    )
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.load_graph_history",
            return_value=Ok(GraphHistory()),
        ),
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
    assert delta.missing_nodes == ("goal manual-goal",)
    assert delta.has_differences


def test_compute_registry_delta_reports_extra_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)

    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="00000000-0000-0000-0000-000000000001",
                instance_name="orphan-goal",
                type_name="goal",
                kind="node",
            ),
        )
    )
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.load_graph_history",
            return_value=Ok(history),
        ),
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
    assert delta.extra_nodes == ("goal orphan-goal",)
    assert delta.has_differences


def test_compute_registry_delta_detects_legacy_id_migration(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / "goals" / "manual-goal.md").write_text(
        "# Manual Goal\n\nAdded by hand.\n",
        encoding="utf-8",
    )
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="00000000-0000-0000-0000-000000000001",
                instance_name="manual-goal",
                type_name="goal",
                kind="node",
            ),
        )
    )
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.load_graph_history",
            return_value=Ok(history),
        ),
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
    assert roadmap.goals == ()

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.load_graph_history",
            return_value=Ok(GraphHistory()),
        ),
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

    def output_graph(self) -> Ok[Graph]:
        return Ok(self._graph)
