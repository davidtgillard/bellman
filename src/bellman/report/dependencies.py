"""Precedence dependency reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO

from bellman.graph.desired import desired_precedence_edges
from bellman.model import PrecedenceEdge, Roadmap


def iter_all_precedence_edges(roadmap: Roadmap) -> list[PrecedenceEdge]:
    """Collect every scope and work-package precedence edge.

    Args:
        roadmap: Loaded roadmap snapshot.

    Returns:
        Edges in stable order: all work scopes, then each project's work
        packages (depth-first).
    """
    edges: list[PrecedenceEdge] = []
    for scope in roadmap.all_work_scopes():
        edges.extend(scope.dependencies)
    for project in roadmap.projects:
        for _project_name, edge in desired_precedence_edges(
            project.work_packages,
            project.name,
        ):
            edges.append(edge)
    return edges


def edges_for_entity(
    roadmap: Roadmap,
    entity: str,
) -> tuple[list[PrecedenceEdge], list[PrecedenceEdge]]:
    """Split edges into predecessors and successors of ``entity``.

    Args:
        roadmap: Loaded roadmap snapshot.
        entity: Natural name or work-package id (``project/slug``).

    Returns:
        ``(predecessors, successors)`` where predecessors are edges whose
        successor is ``entity``, and successors are edges whose predecessor
        is ``entity``.
    """
    predecessors: list[PrecedenceEdge] = []
    successors: list[PrecedenceEdge] = []
    for edge in iter_all_precedence_edges(roadmap):
        if edge.successor == entity:
            predecessors.append(edge)
        if edge.predecessor == entity:
            successors.append(edge)
    return predecessors, successors


def format_edge(edge: PrecedenceEdge) -> str:
    """Format one precedence edge for display.

    Args:
        edge: Precedence edge to format.

    Returns:
        Single-line ``pred -> succ [REL, Hardness]`` string.
    """
    return (
        f"{edge.predecessor} -> {edge.successor} "
        f"[{edge.relation.value}, {edge.hardness.value}]"
    )


def write_dependencies_report(
    roadmap: Roadmap,
    out: TextIO,
    *,
    entity: str | None = None,
) -> None:
    """Write a precedence dependency report to ``out``.

    Args:
        roadmap: Loaded roadmap snapshot.
        out: Destination text stream.
        entity: When set, group edges as predecessors and successors of this
            name; otherwise list every edge.
    """
    if entity is None:
        edges = iter_all_precedence_edges(roadmap)
        for edge in edges:
            out.write(f"{format_edge(edge)}\n")
        return

    predecessors, successors = edges_for_entity(roadmap, entity)
    out.write("Predecessors:\n")
    _write_edge_group(predecessors, out)
    out.write("Successors:\n")
    _write_edge_group(successors, out)


def _write_edge_group(edges: Iterable[PrecedenceEdge], out: TextIO) -> None:
    edges_list = list(edges)
    if not edges_list:
        out.write("  (none)\n")
        return
    for edge in edges_list:
        out.write(f"  {format_edge(edge)}\n")
