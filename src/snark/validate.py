"""Roadmap validation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from snark.errors import SnarkError, SnarkWarning
from snark.model import Hardness, PrecedenceEdge, Roadmap, UnknownEstimate, WorkPackage
from snark.naming import slugify


def _collect_wp_edges(
    packages: tuple[WorkPackage, ...],
    project_name: str,
) -> list[tuple[str, PrecedenceEdge]]:
    edges: list[tuple[str, PrecedenceEdge]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            for edge in wp.dependencies:
                edges.append((project_name, edge))
            walk(wp.children)

    walk(packages)
    return edges


def _collect_wp_slugs(
    packages: tuple[WorkPackage, ...],
) -> list[tuple[str, int]]:
    slugs: list[tuple[str, int]] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            slugs.append((wp.slug, 0))
            walk(wp.children)

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


def _resolve_ref(
    ref: str,
    roadmap: Roadmap,
    project_name: str | None,
) -> bool:
    if "/" in ref:
        parts = ref.split("/", 1)
        proj, slug = parts[0], parts[1]
        return slug in roadmap.work_package_slugs(proj)
    if roadmap.initiative_by_name(ref) is not None:
        return True
    if roadmap.project_by_name(ref) is not None:
        return True
    if roadmap.goal_by_name(ref) is not None:
        return True
    if roadmap.milestone_by_name(ref) is not None:
        return True
    if project_name is not None and ref in roadmap.work_package_slugs(project_name):
        return True
    return False


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of roadmap validation."""

    errors: tuple[SnarkError, ...]
    warnings: tuple[SnarkWarning, ...]


def validate_roadmap(roadmap: Roadmap) -> ValidationResult:
    """Validate a loaded roadmap; return errors and warnings."""
    errors: list[SnarkError] = []
    warnings: list[SnarkWarning] = []

    active_names = {i.name for i in roadmap.initiatives}
    project_names = {p.name for p in roadmap.projects}
    overlap = active_names & project_names
    for name in overlap:
        errors.append(
            SnarkError(
                roadmap.root,
                f"initiative and project both named {name!r}",
            )
        )

    for project in roadmap.projects:
        if not project.criteria_for_success.strip():
            errors.append(
                SnarkError(
                    project.path,
                    "project missing Criteria for Success content",
                )
            )
        slugs = _collect_wp_slugs(project.work_packages)
        seen: set[str] = set()
        for slug, _ in slugs:
            if slug in seen:
                errors.append(
                    SnarkError(
                        project.path,
                        f"duplicate work package slug {slug!r}",
                    )
                )
            seen.add(slug)

        for wp in _walk_packages(project.work_packages):
            if wp.estimate is None:
                errors.append(
                    SnarkError(
                        layout_wp_path(roadmap, project.name, wp.slug),
                        f"work package {wp.slug!r} missing estimate",
                    )
                )
            elif isinstance(wp.estimate, UnknownEstimate):
                warnings.append(
                    SnarkWarning(
                        layout_wp_path(roadmap, project.name, wp.slug),
                        f"work package {wp.slug!r} has unknown estimate",
                    )
                )

        for _, edge in _collect_wp_edges(project.work_packages, project.name):
            if not _resolve_ref(edge.predecessor, roadmap, project.name):
                errors.append(
                    SnarkError(
                        project.path,
                        f"unknown dependency predecessor {edge.predecessor!r}",
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
                SnarkError(
                    project.path,
                    f"mandatory precedence cycle in project {project.name!r}",
                )
            )

    scope_edges: list[PrecedenceEdge] = []
    for scope in roadmap.all_work_scopes():
        for edge in scope.dependencies:
            if not _resolve_ref(edge.predecessor, roadmap, None):
                errors.append(
                    SnarkError(
                        scope.path,
                        f"unknown dependency predecessor {edge.predecessor!r}",
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
            SnarkError(roadmap.root, "mandatory precedence cycle among work scopes")
        )

    for milestone in roadmap.milestones:
        if milestone.date == "YYYY-MM-DD" or len(milestone.date) != 10:
            errors.append(
                SnarkError(milestone.path, "milestone date must be YYYY-MM-DD")
            )

    for goal in roadmap.goals:
        if not goal.title.strip():
            errors.append(SnarkError(goal.path, "goal missing top-level header"))
        else:
            try:
                title_matches = slugify(goal.title) == goal.name
            except ValueError:
                title_matches = False
            if not title_matches:
                errors.append(
                    SnarkError(
                        goal.path,
                        f"goal header {goal.title!r} does not match name {goal.name!r}",
                    )
                )
        if not goal.description.strip():
            errors.append(SnarkError(goal.path, "goal missing content beneath header"))

    return ValidationResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def layout_wp_path(roadmap: Roadmap, project_name: str, slug: str) -> str:
    """Best-effort path for error reporting."""
    return f"{roadmap.root}/projects/{project_name}/work-packages.md ({slug})"


def _normalize_wp_ref(ref: str, project_name: str) -> str:
    if "/" in ref:
        return ref
    return f"{project_name}/{ref}"


def _walk_packages(packages: tuple[WorkPackage, ...]) -> list[WorkPackage]:
    out: list[WorkPackage] = []

    def walk(wps: tuple[WorkPackage, ...]) -> None:
        for wp in wps:
            out.append(wp)
            walk(wp.children)

    walk(packages)
    return out
