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
    desired_link_from_graph_edge,
    desired_links,
    desired_nodes,
    natural_name_from_node_id,
)
from bellman.graph.identity import InstanceIndex
from bellman.graph.legacy import registry_needs_id_migration
from bellman.graph.registry import bellman_link_types, bellman_node_types
from bellman.graph.sync import libfits_available
from bellman.model import Roadmap


@dataclass(frozen=True, slots=True)
class RegistryDelta:
    """Differences between git markdown and the pyfits registry.

    Attributes:
        missing_nodes: Human-readable lines for nodes in git but not registry.
        extra_nodes: Human-readable lines for nodes in registry but not git.
        missing_links: Human-readable lines for links in git but not registry.
        extra_links: Human-readable lines for links in registry but not git.
        needs_id_migration: True when the registry still uses legacy flat node IDs.
        missing_node_ids: Structured nodes present in git but missing from registry.
        extra_node_ids: Structured nodes present in registry but missing from git.
        desired_node_count: Count of nodes implied by markdown.
        actual_node_count: Count of bellman nodes in the registry.
        desired_link_count: Count of links implied by markdown.
        actual_link_count: Count of bellman links in the registry.
    """

    missing_nodes: tuple[str, ...]
    extra_nodes: tuple[str, ...]
    missing_links: tuple[str, ...]
    extra_links: tuple[str, ...]
    needs_id_migration: bool = False
    missing_node_ids: frozenset[DesiredNode] = frozenset()
    extra_node_ids: frozenset[DesiredNode] = frozenset()
    desired_node_count: int = 0
    actual_node_count: int = 0
    desired_link_count: int = 0
    actual_link_count: int = 0

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
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(RegistryDeltaError(index_result.err_value.format()))
    nodes = {
        DesiredNode(inst.type_name, logical_name)
        for logical_name, inst in index_result.ok_value.by_name.items()
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
        graph_result = repo.output_graph(include_nested=True)
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value
    managed = bellman_link_types()
    links: set[DesiredLink] = set()
    for edge in graph.edges:
        if edge.link_type not in managed:
            continue
        desired = desired_link_from_graph_edge(
            link_type=edge.link_type,
            from_id_value=edge.from_id.value,
            to_id_value=edge.to_id.value,
            index=index,
        )
        if desired is not None:
            links.add(desired)
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

    missing_node_set = desired_node_set - actual_node_set
    extra_node_set = actual_node_set - desired_node_set
    missing_link_set = desired_link_set - actual_link_set
    extra_link_set = actual_link_set - desired_link_set

    missing_nodes = tuple(sorted(_format_node(node) for node in missing_node_set))
    extra_nodes = tuple(sorted(_format_node(node) for node in extra_node_set))
    missing_links = tuple(sorted(_format_link(link) for link in missing_link_set))
    extra_links = tuple(sorted(_format_link(link) for link in extra_link_set))

    return Ok(
        RegistryDelta(
            missing_nodes=tuple(missing_nodes),
            extra_nodes=tuple(extra_nodes),
            missing_links=tuple(missing_links),
            extra_links=tuple(extra_links),
            needs_id_migration=registry_needs_id_migration(
                actual_node_set, desired_node_set
            ),
            missing_node_ids=frozenset(missing_node_set),
            extra_node_ids=frozenset(extra_node_set),
            desired_node_count=len(desired_node_set),
            actual_node_count=len(actual_node_set),
            desired_link_count=len(desired_link_set),
            actual_link_count=len(actual_link_set),
        )
    )
