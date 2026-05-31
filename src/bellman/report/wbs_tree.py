"""Work-breakdown-structure tree report with PERT rollups."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TextIO

from bellman.model import (
    Project,
    Roadmap,
    ThreePointEstimate,
    UnknownEstimate,
    WorkPackage,
)
from bellman.report.wbs import format_pert, pert_numeric

_UNKNOWN_DISPLAY = "?"


@dataclass(frozen=True, slots=True)
class Rollup:
    """PERT rollup for one work package."""

    pert: float | None
    unit: str | None
    display: str


@dataclass(frozen=True, slots=True)
class TreeLine:
    """One rendered line in the WBS tree."""

    connector: str
    section: str
    title: str
    display: str


def rollup(wp: WorkPackage) -> Rollup:
    """Compute PERT display for a work package, rolling up children when present.

    Args:
        wp: Work package node.

    Returns:
        Rollup with numeric PERT (when known), unit, and display string.

    Raises:
        ValueError: When summed children use mixed duration units.
    """
    if wp.sub_packages:
        return _rollup_children(wp.sub_packages, wp.slug)
    return _rollup_leaf(wp)


def _rollup_leaf(wp: WorkPackage) -> Rollup:
    estimate = wp.estimate
    if estimate is None or isinstance(estimate, UnknownEstimate):
        return Rollup(None, None, _UNKNOWN_DISPLAY)
    assert isinstance(estimate, ThreePointEstimate)
    value = pert_numeric(estimate)
    unit = estimate.unit
    return Rollup(value, unit, format_pert(value, unit))


def _rollup_children(
    packages: tuple[WorkPackage, ...],
    parent_slug: str,
) -> Rollup:
    total = 0.0
    unit: str | None = None
    for wp in packages:
        child = rollup(wp)
        if child.pert is None:
            return Rollup(None, None, _UNKNOWN_DISPLAY)
        if unit is None:
            unit = child.unit
        elif child.unit != unit:
            msg = f"mixed duration units under work package {parent_slug!r}"
            raise ValueError(msg)
        total += child.pert
    if unit is None:
        return Rollup(None, None, _UNKNOWN_DISPLAY)
    return Rollup(total, unit, format_pert(total, unit))


def _sum_rollups(
    rollups: list[Rollup],
    *,
    context: str,
) -> Rollup:
    """Sum numeric PERT values that share one unit.

    Args:
        rollups: Rollups to combine.
        context: Label for mixed-unit errors (e.g. project name).

    Raises:
        ValueError: When rollups use mixed duration units.
    """
    total = 0.0
    unit: str | None = None
    for item in rollups:
        if item.pert is None:
            return Rollup(None, None, _UNKNOWN_DISPLAY)
        if unit is None:
            unit = item.unit
        elif item.unit != unit:
            msg = f"mixed duration units for {context}"
            raise ValueError(msg)
        total += item.pert
    if unit is None:
        return Rollup(None, None, _UNKNOWN_DISPLAY)
    return Rollup(total, unit, format_pert(total, unit))


def project_total_pert(project: Project) -> Rollup:
    """Sum rolled-up PERT across root-level work packages.

    Args:
        project: Project whose root work packages are totaled.

    Returns:
        Combined project rollup.

    Raises:
        ValueError: When root packages use mixed duration units.
    """
    if not project.work_packages:
        return Rollup(None, None, _UNKNOWN_DISPLAY)
    rollups = [rollup(wp) for wp in project.work_packages]
    return _sum_rollups(rollups, context=f"project {project.name!r}")


def _iter_tree_lines(
    project: Project,
    *,
    prefix: str = "",
    packages: tuple[WorkPackage, ...] | None = None,
    section_prefix: str = "",
) -> Iterator[TreeLine]:
    """Yield tree lines for one project's work packages in WBS order."""
    if packages is None:
        packages = project.work_packages
    sorted_packages = sorted(packages, key=lambda item: item.slug)
    last_index = len(sorted_packages)
    for index, wp in enumerate(sorted_packages, start=1):
        section = f"{section_prefix}.{index}" if section_prefix else str(index)
        is_last = index == last_index
        connector = "└── " if is_last else "├── "
        child_rollup = rollup(wp)
        yield TreeLine(
            connector=prefix + connector,
            section=section,
            title=wp.title,
            display=child_rollup.display,
        )
        child_prefix = prefix + ("    " if is_last else "│   ")
        yield from _iter_tree_lines(
            project,
            prefix=child_prefix,
            packages=wp.sub_packages,
            section_prefix=section,
        )


def _projects_for_report(
    roadmap: Roadmap,
    *,
    project_name: str | None,
) -> list[Project]:
    projects = sorted(roadmap.projects, key=lambda item: item.name)
    if project_name is None:
        return projects
    project = roadmap.project_by_name(project_name)
    if project is None:
        msg = f"project not found: {project_name!r}"
        raise ValueError(msg)
    return [project]


def write_wbs_tree(
    roadmap: Roadmap,
    output: TextIO,
    *,
    project_name: str | None = None,
) -> None:
    """Write a WBS tree with PERT estimates to ``output``.

    Args:
        roadmap: Loaded roadmap snapshot.
        output: Writable text stream (file or stdout).
        project_name: When set, restrict output to this project name.

    Raises:
        ValueError: When ``project_name`` is missing or rollups mix units.
    """
    projects = _projects_for_report(roadmap, project_name=project_name)
    for project_index, project in enumerate(projects):
        if project_index > 0:
            output.write("\n")
        total = project_total_pert(project)
        output.write(f"project: {project.name}\n")
        output.write(f"total estimate: {total.display}\n")
        for line in _iter_tree_lines(project):
            output.write(
                f"{line.connector}{line.section} {line.title}  {line.display}\n"
            )
        output.write(f"total estimate: {total.display}\n")
