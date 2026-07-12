"""Desired pyfits graph state derived from markdown roadmap files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bellman import layout
from bellman.graph import link_naming
from bellman.model import Initiative, PrecedenceEdge, Project, Roadmap, WorkPackage

_ENTITY_KINDS = ("initiative", "project", "goal", "milestone")


@dataclass(frozen=True, slots=True)
class DesiredNode:
    """A node that should exist in the registry for the loaded roadmap."""

    type_name: str
    node_id: str


@dataclass(frozen=True, slots=True)
class DesiredLink:
    """A link that should exist in the registry for the loaded roadmap."""

    link_type: str
    from_id: str
    to_id: str


def entity_node_id(type_name: str, name: str) -> str:
    """Build a type-qualified opaque node id for pyfits.

    Format: ``{type_name}/{name}`` (kind-root path).
    """
    return f"{type_name}/{name}"


def natural_name_from_node_id(node_id: str) -> str:
    """Extract the natural entity name from an opaque node id for display."""
    if "/" in node_id:
        return node_id.rsplit("/", 1)[-1]
    for type_name in _ENTITY_KINDS:
        prefix = f"{type_name}--"
        if node_id.startswith(prefix):
            return node_id[len(prefix) :]
    return node_id


def local_name_from_node_id(node_id: str) -> str:
    """Return the single-segment instance name for create/rename."""
    if "/" in node_id:
        return node_id.rsplit("/", 1)[-1]
    if "--" in node_id:
        return node_id.split("--", 1)[-1]
    return node_id


def scope_node_id(scope: Initiative | Project) -> str:
    """Opaque node id for an initiative or project."""
    if isinstance(scope, Project):
        return entity_node_id("project", scope.name)
    return entity_node_id("initiative", scope.name)


def wp_node_id(project_name: str, slug: str) -> str:
    """Opaque node id for a work package nested under its project."""
    return f"project/{project_name}/{slug}"


def milestone_node_id(name: str) -> str:
    """Opaque node id for a milestone."""
    return entity_node_id("milestone", name)


def goal_node_id(name: str) -> str:
    """Opaque node id for a goal."""
    return entity_node_id("goal", name)


def flatten_wps(
    packages: tuple[WorkPackage, ...],
    parent: WorkPackage | None,
    project_name: str,
) -> list[tuple[WorkPackage, WorkPackage | None]]:
    """Walk work-package tree in preorder with parent pointers."""
    out: list[tuple[WorkPackage, WorkPackage | None]] = []
    for wp in packages:
        out.append((wp, parent))
        out.extend(flatten_wps(wp.sub_packages, wp, project_name))
    return out


def resolve_wp_ref(project_name: str, ref: str) -> str:
    """Resolve a work-package dependency reference to an opaque node id."""
    slug = ref.split("/", 1)[-1] if "/" in ref else ref
    return wp_node_id(project_name, slug)


def resolve_entity_ref(roadmap: Roadmap, ref: str) -> str:
    """Resolve a bare markdown entity reference to a qualified opaque node id.

    Args:
        roadmap: Loaded roadmap snapshot.
        ref: Bare entity name from markdown dependency syntax.

    Returns:
        Qualified node id when exactly one entity matches, otherwise ``ref``
        unchanged when no entity matches.

    Raises:
        ValueError: When more than one entity kind matches ``ref``.
    """
    matches: list[tuple[str, str]] = []
    if roadmap.project_by_name(ref) is not None:
        matches.append(("project", entity_node_id("project", ref)))
    if roadmap.initiative_by_name(ref) is not None:
        matches.append(("initiative", entity_node_id("initiative", ref)))
    for archived in roadmap.archived_initiatives:
        if archived.name == ref and roadmap.project_by_name(ref) is None:
            matches.append(("initiative", entity_node_id("initiative", ref)))
    if roadmap.milestone_by_name(ref) is not None:
        matches.append(("milestone", entity_node_id("milestone", ref)))
    if roadmap.goal_by_name(ref) is not None:
        matches.append(("goal", entity_node_id("goal", ref)))
    if len(matches) > 1:
        kinds = ", ".join(kind for kind, _ in matches)
        msg = f"ambiguous dependency reference {ref!r}: matches {kinds}"
        raise ValueError(msg)
    if len(matches) == 1:
        return matches[0][1]
    return ref


def resolve_scope_ref(roadmap: Roadmap, ref: str) -> str:
    """Resolve a work-scope dependency reference to an opaque node id."""
    return resolve_entity_ref(roadmap, ref)


def resolve_entity_ref_from_layout(root: Path, ref: str) -> str:
    """Resolve a bare entity name using filesystem layout (no full roadmap load).

    Args:
        root: Roadmap root directory.
        ref: Bare entity name from markdown dependency syntax.

    Returns:
        Qualified node id when exactly one entity matches, otherwise ``ref``
        unchanged when no entity matches.

    Raises:
        ValueError: When more than one entity kind matches ``ref``.
    """
    matches: list[tuple[str, str]] = []
    if layout.project_dir(root, ref).is_dir():
        matches.append(("project", entity_node_id("project", ref)))
    if layout.initiative_path(root, ref).is_file():
        matches.append(("initiative", entity_node_id("initiative", ref)))
    if (
        layout.archived_initiative_path(root, ref).is_file()
        and not layout.project_dir(root, ref).is_dir()
    ):
        matches.append(("initiative", entity_node_id("initiative", ref)))
    if layout.milestone_path(root, ref).is_file():
        matches.append(("milestone", entity_node_id("milestone", ref)))
    if layout.goal_path(root, ref).is_file():
        matches.append(("goal", entity_node_id("goal", ref)))
    if len(matches) > 1:
        kinds = ", ".join(kind for kind, _ in matches)
        msg = f"ambiguous dependency reference {ref!r}: matches {kinds}"
        raise ValueError(msg)
    if len(matches) == 1:
        return matches[0][1]
    return ref


def desired_nodes(roadmap: Roadmap) -> set[DesiredNode]:
    """Return all bellman nodes implied by ``roadmap`` markdown."""
    nodes: set[DesiredNode] = set()
    for initiative in roadmap.initiatives:
        nodes.add(DesiredNode("initiative", scope_node_id(initiative)))
    for archived in roadmap.archived_initiatives:
        if roadmap.project_by_name(archived.name) is None:
            nodes.add(DesiredNode("initiative", scope_node_id(archived)))
    for project in roadmap.projects:
        nodes.add(DesiredNode("project", scope_node_id(project)))
        for wp, _ in flatten_wps(project.work_packages, None, project.name):
            nodes.add(DesiredNode("work_package", wp_node_id(project.name, wp.slug)))
    for milestone in roadmap.milestones:
        nodes.add(DesiredNode("milestone", milestone_node_id(milestone.name)))
    for goal in roadmap.goals:
        nodes.add(DesiredNode("goal", goal_node_id(goal.name)))
    return nodes


def desired_node_ids(roadmap: Roadmap) -> set[str]:
    """Return opaque node ids that should exist after a full roadmap sync."""
    return {node.node_id for node in desired_nodes(roadmap)}


def _desired_wp_links(project: Project) -> set[DesiredLink]:
    links: set[DesiredLink] = set()
    flat = flatten_wps(project.work_packages, None, project.name)
    for wp, parent in flat:
        wid = wp_node_id(project.name, wp.slug)
        if parent is not None:
            parent_id = wp_node_id(project.name, parent.slug)
            links.add(DesiredLink("parent_of", parent_id, wid))
        for edge in wp.dependencies:
            pred = resolve_wp_ref(project.name, edge.predecessor)
            lt = link_naming.precedes_link_type(edge.relation, edge.hardness)
            links.add(DesiredLink(lt, pred, wid))
    return links


def _desired_scope_links(
    roadmap: Roadmap, scope: Initiative | Project
) -> set[DesiredLink]:
    links: set[DesiredLink] = set()
    sid = scope_node_id(scope)
    for edge in scope.dependencies:
        pred = resolve_scope_ref(roadmap, edge.predecessor)
        lt = f"{link_naming.precedes_link_type(edge.relation, edge.hardness)}_scope"
        links.add(DesiredLink(lt, pred, sid))
    return links


def desired_links(roadmap: Roadmap) -> set[DesiredLink]:
    """Return all bellman links implied by ``roadmap`` markdown."""
    links: set[DesiredLink] = set()
    for project in roadmap.projects:
        links |= _desired_wp_links(project)
    for scope in roadmap.all_work_scopes():
        links |= _desired_scope_links(roadmap, scope)
    return links


def desired_precedence_edges(
    packages: tuple[WorkPackage, ...],
    project_name: str,
) -> list[tuple[str, PrecedenceEdge]]:
    """Collect work-package precedence edges with project context."""
    edges: list[tuple[str, PrecedenceEdge]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            for edge in wp.dependencies:
                edges.append((project_name, edge))
            walk(wp.sub_packages)

    walk(packages)
    return edges
