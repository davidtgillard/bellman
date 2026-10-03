"""Uniform view of roadmap entities that can carry attribute assignments."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from bellman.model import (
    AttributeAssignment,
    Project,
    Roadmap,
    WorkPackage,
)

__all__ = ["EntityRef", "iter_entities", "work_package_path"]


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A roadmap entity together with its attribute assignments.

    Attributes:
        kind: ``initiative``, ``project``, ``work_package``, ``milestone``, or
            ``goal``.
        name: Natural name; work packages use ``{project}/{slug}``.
        path: Source path for error reporting.
        classifications: Assignments in document order.
    """

    kind: str
    name: str
    path: str
    classifications: tuple[AttributeAssignment, ...] = ()

    def assignments(self, attribute: str) -> tuple[AttributeAssignment, ...]:
        """Return this entity's assignments of ``attribute``.

        Args:
            attribute: Attribute name.

        Returns:
            Matching assignments in document order (possibly empty).
        """
        return tuple(a for a in self.classifications if a.name == attribute)


def work_package_path(root: str, project_name: str, slug: str) -> str:
    """Best-effort path string for a work package, for error reporting.

    Args:
        root: Roadmap root directory.
        project_name: Owning project name.
        slug: Work package slug.

    Returns:
        A display path naming the project's ``work-packages.yaml`` and slug.
    """
    return f"{root}/projects/{project_name}/work-packages.yaml ({slug})"


def _walk(packages: tuple[WorkPackage, ...]) -> Iterator[WorkPackage]:
    for wp in packages:
        yield wp
        yield from _walk(wp.sub_packages)


def iter_entities(roadmap: Roadmap, kind: str | None = None) -> Iterator[EntityRef]:
    """Iterate every loaded entity that can carry attribute assignments.

    Covers live initiatives, projects and their work packages (nested ones
    included), milestones, goals, and archived initiatives that have no live
    project.

    Args:
        roadmap: Loaded roadmap.
        kind: When set, yield only entities of this kind.

    Yields:
        One :class:`EntityRef` per entity.
    """
    refs: list[EntityRef] = []
    for scope in roadmap.all_work_scopes():
        scope_kind = "project" if isinstance(scope, Project) else "initiative"
        refs.append(
            EntityRef(scope_kind, scope.name, scope.path, scope.classifications)
        )
    for project in roadmap.projects:
        for wp in _walk(project.work_packages):
            refs.append(
                EntityRef(
                    "work_package",
                    f"{project.name}/{wp.slug}",
                    work_package_path(roadmap.root, project.name, wp.slug),
                    wp.classifications,
                )
            )
    for milestone in roadmap.milestones:
        refs.append(
            EntityRef(
                "milestone", milestone.name, milestone.path, milestone.classifications
            )
        )
    for goal in roadmap.goals:
        refs.append(EntityRef("goal", goal.name, goal.path, goal.classifications))
    for ref in refs:
        if kind is None or ref.kind == kind:
            yield ref
