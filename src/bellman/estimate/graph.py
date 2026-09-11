"""Build a leaf activity graph from a project's WBS and precedence edges."""

from __future__ import annotations

from dataclasses import dataclass

from bellman.model import (
    PrecedenceEdge,
    Project,
    RelationType,
    ThreePointEstimate,
    UnknownEstimate,
    WorkPackage,
)


@dataclass(frozen=True, slots=True)
class EstimateActivity:
    """A schedulable leaf work package.

    Attributes:
        activity_id: ``project/slug`` identifier.
        estimate: Three-point duration used for Beta-PERT sampling.
    """

    activity_id: str
    estimate: ThreePointEstimate


@dataclass(frozen=True, slots=True)
class EstimateConstraint:
    """A leaf-to-leaf precedence constraint.

    Attributes:
        predecessor: Predecessor activity id.
        successor: Successor activity id.
        relation: CPM relation type.
    """

    predecessor: str
    successor: str
    relation: RelationType


@dataclass(frozen=True, slots=True)
class EstimateGraph:
    """Validated leaf activities and expanded in-project constraints.

    Attributes:
        project: Project natural name.
        unit: Shared duration unit of every leaf estimate.
        activities: Leaf activities in stable slug order.
        constraints: Expanded leaf-to-leaf constraints.
    """

    project: str
    unit: str
    activities: tuple[EstimateActivity, ...]
    constraints: tuple[EstimateConstraint, ...]


def _activity_id(project_name: str, slug: str) -> str:
    return f"{project_name}/{slug}"


def _walk_packages(packages: tuple[WorkPackage, ...]) -> list[WorkPackage]:
    out: list[WorkPackage] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            out.append(wp)
            walk(wp.sub_packages)

    walk(packages)
    return out


def _descendant_leaves(wp: WorkPackage) -> list[WorkPackage]:
    if not wp.sub_packages:
        return [wp]
    leaves: list[WorkPackage] = []
    for child in wp.sub_packages:
        leaves.extend(_descendant_leaves(child))
    return leaves


def _normalize_in_project_ref(ref: str, project_name: str, slugs: set[str]) -> str:
    if "/" in ref:
        other_project, slug = ref.split("/", 1)
        if other_project != project_name:
            msg = (
                f"cross-project predecessor {ref!r} is not supported "
                f"for project {project_name!r}"
            )
            raise ValueError(msg)
    else:
        slug = ref
    if slug not in slugs:
        msg = (
            f"predecessor {ref!r} is outside project {project_name!r} "
            f"or is not a work package"
        )
        raise ValueError(msg)
    return slug


def _package_edges(
    packages: tuple[WorkPackage, ...],
) -> list[tuple[str, PrecedenceEdge]]:
    edges: list[tuple[str, PrecedenceEdge]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            for edge in wp.dependencies:
                edges.append((wp.slug, edge))
            walk(wp.sub_packages)

    walk(packages)
    return edges


def _has_cycle(constraints: list[EstimateConstraint]) -> bool:
    graph: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for edge in constraints:
        graph.setdefault(edge.predecessor, []).append(edge.successor)
        nodes.add(edge.predecessor)
        nodes.add(edge.successor)

    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> bool:
        if node in stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        stack.add(node)
        for nxt in graph.get(node, ()):
            if dfs(nxt):
                return True
        stack.remove(node)
        return False

    return any(dfs(node) for node in nodes)


def build_estimate_graph(project: Project) -> EstimateGraph:
    """Collect leaf activities and expand in-project precedence to leaves.

    Parent endpoints expand to descendant leaves. A successor that is itself
    a descendant of a parent predecessor is omitted from that expansion so a
    child depending on its parent does not become a self-loop.

    Args:
        project: Project whose work packages are estimated.

    Returns:
        Graph ready for sampling and list scheduling.

    Raises:
        ValueError: When the WBS is empty, a leaf estimate is missing or
            unknown, units are mixed, a predecessor is outside the project,
            or expanded edges form a cycle.
    """
    if not project.work_packages:
        msg = f"project {project.name!r} has no work packages"
        raise ValueError(msg)

    all_packages = _walk_packages(project.work_packages)
    by_slug = {wp.slug: wp for wp in all_packages}
    slugs = set(by_slug)

    activities: list[EstimateActivity] = []
    unit: str | None = None
    for wp in all_packages:
        if wp.sub_packages:
            continue
        estimate = wp.estimate
        if estimate is None:
            msg = f"work package {wp.slug!r} missing estimate"
            raise ValueError(msg)
        if isinstance(estimate, UnknownEstimate):
            msg = f"work package {wp.slug!r} has unknown estimate"
            raise ValueError(msg)
        if unit is None:
            unit = estimate.unit
        elif estimate.unit != unit:
            msg = f"mixed duration units for project {project.name!r}"
            raise ValueError(msg)
        activities.append(
            EstimateActivity(
                activity_id=_activity_id(project.name, wp.slug),
                estimate=estimate,
            )
        )

    if not activities:
        msg = f"project {project.name!r} has no estimated leaf work packages"
        raise ValueError(msg)
    assert unit is not None

    activities.sort(key=lambda item: item.activity_id)
    constraints: list[EstimateConstraint] = []
    for owner_slug, edge in _package_edges(project.work_packages):
        pred_slug = _normalize_in_project_ref(edge.predecessor, project.name, slugs)
        succ_ref = edge.successor
        if "/" in succ_ref:
            _, succ_slug = succ_ref.split("/", 1)
        else:
            succ_slug = owner_slug
        if succ_slug not in slugs:
            msg = f"successor {succ_ref!r} is not a work package in {project.name!r}"
            raise ValueError(msg)
        pred_leaves = _descendant_leaves(by_slug[pred_slug])
        succ_leaves = _descendant_leaves(by_slug[succ_slug])
        for pred in pred_leaves:
            for succ in succ_leaves:
                if pred.slug == succ.slug:
                    continue
                constraints.append(
                    EstimateConstraint(
                        predecessor=_activity_id(project.name, pred.slug),
                        successor=_activity_id(project.name, succ.slug),
                        relation=edge.relation,
                    )
                )

    if _has_cycle(constraints):
        msg = f"precedence cycle in project {project.name!r}"
        raise ValueError(msg)

    return EstimateGraph(
        project=project.name,
        unit=unit,
        activities=tuple(activities),
        constraints=tuple(constraints),
    )
