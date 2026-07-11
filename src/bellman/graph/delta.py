"""Compare markdown roadmap state to the live pyfits registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyfits import Repo
from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

from bellman.graph.desired import (
    DesiredLink,
    DesiredNode,
    desired_links,
    desired_nodes,
    natural_name_from_node_id,
)
from bellman.graph.history import load_graph_history
from bellman.graph.identity import InstanceIndex
from bellman.graph.legacy import registry_needs_id_migration
from bellman.graph.registry import bellman_link_types, bellman_node_types
from bellman.graph.sync import libfits_available
from bellman.model import Roadmap


@dataclass(frozen=True, slots=True)
class RegistryDelta:
    """Differences between git markdown and the pyfits registry."""

    missing_nodes: tuple[str, ...]
    extra_nodes: tuple[str, ...]
    missing_links: tuple[str, ...]
    extra_links: tuple[str, ...]
    needs_id_migration: bool = False

    @property
    def has_differences(self) -> bool:
        """Return True when any delta line would be reported."""
        return bool(
            self.missing_nodes
            or self.extra_nodes
            or self.missing_links
            or self.extra_links
        )

    @property
    def count(self) -> int:
        """Total number of reported delta lines."""
        return (
            len(self.missing_nodes)
            + len(self.extra_nodes)
            + len(self.missing_links)
            + len(self.extra_links)
        )


@dataclass(frozen=True, slots=True)
class RegistryDeltaError:
    """Failure computing registry deltas."""

    message: str

    def format(self) -> str:
        return self.message


def _format_node(node: DesiredNode) -> str:
    return f"{node.type_name} {natural_name_from_node_id(node.node_id)}"


def _format_link(link: DesiredLink) -> str:
    return f"{link.link_type} {link.from_id} -> {link.to_id}"


def _actual_nodes(root: Path) -> Result[set[DesiredNode], RegistryDeltaError]:
    history_result = load_graph_history(root)
    if isinstance(history_result, Err):
        return Err(RegistryDeltaError(history_result.err_value.format()))
    nodes = {
        DesiredNode(inst.type_name, inst.instance_name)
        for inst in history_result.ok_value.instances
        if inst.kind == "node" and inst.type_name in bellman_node_types()
    }
    return Ok(nodes)


def _actual_links(
    root: Path,
) -> Result[set[DesiredLink], RegistryDeltaError | FitsError]:
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(RegistryDeltaError(index_result.err_value.format()))
    index = index_result.ok_value

    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        graph_result = repo.output_graph()
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value
    managed = bellman_link_types()
    links: set[DesiredLink] = set()
    for edge in graph.edges:
        if edge.link_type not in managed:
            continue
        from_name = index.name_for_guid(edge.from_id.value)
        to_name = index.name_for_guid(edge.to_id.value)
        if from_name is None or to_name is None:
            continue
        links.add(DesiredLink(edge.link_type, from_name, to_name))
    return Ok(links)


def compute_registry_delta(
    root: Path,
    roadmap: Roadmap,
) -> Result[RegistryDelta, RegistryDeltaError | FitsError]:
    """Compare ``roadmap`` markdown to the live registry at ``root``.

    Args:
        root: Roadmap root directory with an initialized ``.fits/`` tree.
        roadmap: Parsed markdown roadmap (source of truth).

    Returns:
        ``Ok(RegistryDelta)`` with human-readable delta lines.
        ``Err(RegistryDeltaError)`` when history cannot be loaded.
        ``Err(FitsError)`` when libfits graph access fails.
    """
    if not libfits_available():
        return Err(
            RegistryDeltaError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits"
            )
        )
    if not (root / ".fits").is_dir():
        return Err(RegistryDeltaError("Roadmap not initialized; run bellman init"))

    desired_node_set = desired_nodes(roadmap)
    desired_link_set = desired_links(roadmap)

    actual_nodes_result = _actual_nodes(root)
    if isinstance(actual_nodes_result, Err):
        return actual_nodes_result
    actual_node_set = actual_nodes_result.ok_value

    actual_links_result = _actual_links(root)
    if isinstance(actual_links_result, Err):
        return actual_links_result
    actual_link_set = actual_links_result.ok_value

    missing_nodes = tuple(
        sorted(_format_node(node) for node in desired_node_set - actual_node_set)
    )
    extra_nodes = tuple(
        sorted(_format_node(node) for node in actual_node_set - desired_node_set)
    )
    missing_links = tuple(
        sorted(_format_link(link) for link in desired_link_set - actual_link_set)
    )
    extra_links = tuple(
        sorted(_format_link(link) for link in actual_link_set - desired_link_set)
    )

    return Ok(
        RegistryDelta(
            missing_nodes=tuple(missing_nodes),
            extra_nodes=tuple(extra_nodes),
            missing_links=tuple(missing_links),
            extra_links=tuple(extra_links),
            needs_id_migration=registry_needs_id_migration(
                actual_node_set, desired_node_set
            ),
        )
    )
