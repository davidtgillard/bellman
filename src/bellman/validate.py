"""Roadmap validation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bellman.errors import BellmanError, BellmanWarning
from bellman.graph.desired import resolve_entity_ref
from bellman.model import (
    Hardness,
    PrecedenceEdge,
    Roadmap,
    UnknownEstimate,
    WorkPackage,
)
from bellman.naming import slugify


def _collect_wp_edges(
    packages: tuple[WorkPackage, ...],
    project_name: str,
) -> list[tuple[str, PrecedenceEdge]]:
    edges: list[tuple[str, PrecedenceEdge]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            for edge in wp.dependencies:
                edges.append((project_name, edge))
            walk(wp.sub_packages)

    walk(packages)
    return edges


def _collect_wp_slugs(
    packages: tuple[WorkPackage, ...],
) -> list[tuple[str, int]]:
    slugs: list[tuple[str, int]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            slugs.append((wp.slug, 0))
            walk(wp.sub_packages)

    walk(packages)
    return slugs


def _has_cycle(edges: list[PrecedenceEdge], *, mandatory_only: bool) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for edge in edges:
        if mandatory_only and edge.hardness is not Hardness.MANDATORY:
            continue
        graph[edge.predecessor].append(edge.successor)
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
        for nxt in graph[node]:
            if dfs(nxt):
                return True
        stack.remove(node)
        return False

    return any(dfs(n) for n in nodes)


def _dependency_ref_error(
    ref: str,
    roadmap: Roadmap,
    project_name: str | None,
) -> str | None:
    """Return an error message when ``ref`` is invalid; otherwise ``None``."""
    if "/" in ref:
        proj, slug = ref.split("/", 1)
        if slug in roadmap.work_package_slugs(proj):
            return None
        return f"unknown dependency predecessor {ref!r}"
    if project_name is not None and ref in roadmap.work_package_slugs(project_name):
        return None
    try:
        resolved = resolve_entity_ref(roadmap, ref)
    except ValueError as exc:
        return str(exc)
    if resolved == ref:
        return f"unknown dependency predecessor {ref!r}"
    return None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of roadmap validation."""

    errors: tuple[BellmanError, ...]
    warnings: tuple[BellmanWarning, ...]


def validate_roadmap(roadmap: Roadmap) -> ValidationResult:
    """Validate a loaded roadmap; return errors and warnings."""
    errors: list[BellmanError] = []
    warnings: list[BellmanWarning] = []

    active_names = {i.name for i in roadmap.initiatives}
    project_names = {p.name for p in roadmap.projects}
    overlap = active_names & project_names
    for name in overlap:
        errors.append(
            BellmanError(
                roadmap.root,
                f"initiative and project both named {name!r}",
            )
        )

    for project in roadmap.projects:
        if not project.criteria_for_success.strip():
            errors.append(
                BellmanError(
                    project.path,
                    "project missing Criteria for Success content",
                )
            )
        slugs = _collect_wp_slugs(project.work_packages)
        seen: set[str] = set()
        for slug, _ in slugs:
            if slug in seen:
                errors.append(
                    BellmanError(
                        project.path,
                        f"duplicate work package slug {slug!r}",
                    )
                )
            seen.add(slug)

        for wp in _walk_packages(project.work_packages):
            if wp.sub_packages:
                if wp.estimate is not None:
                    errors.append(
                        BellmanError(
                            layout_wp_path(roadmap, project.name, wp.slug),
                            f"work package {wp.slug!r} has sub-packages and "
                            f"must not have its own estimate",
                        )
                    )
            elif wp.estimate is None:
                errors.append(
                    BellmanError(
                        layout_wp_path(roadmap, project.name, wp.slug),
                        f"work package {wp.slug!r} missing estimate",
                    )
                )
            elif isinstance(wp.estimate, UnknownEstimate):
                warnings.append(
                    BellmanWarning(
                        layout_wp_path(roadmap, project.name, wp.slug),
                        f"work package {wp.slug!r} has unknown estimate",
                    )
                )

        for _, edge in _collect_wp_edges(project.work_packages, project.name):
            ref_error = _dependency_ref_error(edge.predecessor, roadmap, project.name)
            if ref_error is not None:
                errors.append(
                    BellmanError(
                        project.path,
                        ref_error,
                    )
                )
        wp_edges = [
            e for _, e in _collect_wp_edges(project.work_packages, project.name)
        ]
        normalized = [
            PrecedenceEdge(
                predecessor=_normalize_wp_ref(e.predecessor, project.name),
                successor=_normalize_wp_ref(e.successor, project.name),
                relation=e.relation,
                hardness=e.hardness,
            )
            for e in wp_edges
        ]
        if _has_cycle(normalized, mandatory_only=True):
            errors.append(
                BellmanError(
                    project.path,
                    f"mandatory precedence cycle in project {project.name!r}",
                )
            )

    scope_edges: list[PrecedenceEdge] = []
    for scope in roadmap.all_work_scopes():
        for edge in scope.dependencies:
            ref_error = _dependency_ref_error(edge.predecessor, roadmap, None)
            if ref_error is not None:
                errors.append(
                    BellmanError(
                        scope.path,
                        ref_error,
                    )
                )
            scope_edges.append(
                PrecedenceEdge(
                    predecessor=edge.predecessor,
                    successor=scope.name,
                    relation=edge.relation,
                    hardness=edge.hardness,
                )
            )
    if _has_cycle(scope_edges, mandatory_only=True):
        errors.append(
            BellmanError(roadmap.root, "mandatory precedence cycle among work scopes")
        )

    for milestone in roadmap.milestones:
        if milestone.date == "YYYY-MM-DD" or len(milestone.date) != 10:
            errors.append(
                BellmanError(milestone.path, "milestone date must be YYYY-MM-DD")
            )

    for goal in roadmap.goals:
        if not goal.title.strip():
            errors.append(BellmanError(goal.path, "goal missing top-level header"))
        else:
            try:
                title_matches = slugify(goal.title) == goal.name
            except ValueError:
                title_matches = False
            if not title_matches:
                errors.append(
                    BellmanError(
                        goal.path,
                        f"goal header {goal.title!r} does not match name {goal.name!r}",
                    )
                )
        if not goal.description.strip():
            errors.append(
                BellmanError(goal.path, "goal missing content beneath header")
            )

    return ValidationResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def layout_wp_path(roadmap: Roadmap, project_name: str, slug: str) -> str:
    """Best-effort path for error reporting."""
    return f"{roadmap.root}/projects/{project_name}/work-packages.yaml ({slug})"


def _normalize_wp_ref(ref: str, project_name: str) -> str:
    if "/" in ref:
        return ref
    return f"{project_name}/{ref}"


def _walk_packages(packages: tuple[WorkPackage, ...]) -> list[WorkPackage]:
    out: list[WorkPackage] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            out.append(wp)
            walk(wp.sub_packages)

    walk(packages)
    return out
