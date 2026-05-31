"""Work-breakdown-structure CSV export."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from bellman.model import (
    Estimate,
    Project,
    Roadmap,
    ThreePointEstimate,
    UnknownEstimate,
    WorkPackage,
)

WBS_HEADERS: tuple[str, ...] = (
    "work package",
    "numbered section",
    "title",
    "description",
    "notes",
    "worst-case estimate",
    "expected-case estimate",
    "best-case estimate",
    "PERT estimate",
)

_TITLE_INDENT = "  "


def _format_duration(amount: float, unit: str) -> str:
    if amount == int(amount):
        return f"{int(amount)}{unit}"
    text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def _estimate_columns(estimate: Estimate | None) -> tuple[str, str, str, str]:
    """Return worst, expected, best, and PERT estimate strings for a row."""
    if estimate is None or isinstance(estimate, UnknownEstimate):
        return ("", "", "", "")
    assert isinstance(estimate, ThreePointEstimate)
    unit = estimate.unit
    worst = _format_duration(estimate.pessimistic, unit)
    expected = _format_duration(estimate.most_likely, unit)
    best = _format_duration(estimate.optimistic, unit)
    pert_value = (
        estimate.optimistic + 4 * estimate.most_likely + estimate.pessimistic
    ) / 6
    pert = _format_duration(pert_value, unit)
    return (worst, expected, best, pert)


def _indented_title(title: str, depth: int) -> str:
    return f"{_TITLE_INDENT * depth}{title}"


def _wbs_row(
    wp: WorkPackage,
    *,
    project_name: str,
    section: str,
    depth: int,
) -> list[str]:
    worst, expected, best, pert = _estimate_columns(wp.estimate)
    return [
        f"{project_name}/{wp.slug}",
        section,
        _indented_title(wp.title, depth),
        wp.description,
        wp.notes,
        worst,
        expected,
        best,
        pert,
    ]


def _iter_project_wbs_rows(
    project: Project,
    *,
    prefix: str = "",
    packages: tuple[WorkPackage, ...] | None = None,
    depth: int = 0,
) -> Iterator[list[str]]:
    """Yield CSV rows for one project's work packages in WBS order."""
    if packages is None:
        packages = project.work_packages
    for index, wp in enumerate(sorted(packages, key=lambda item: item.slug), start=1):
        section = f"{prefix}.{index}" if prefix else str(index)
        yield _wbs_row(
            wp,
            project_name=project.name,
            section=section,
            depth=depth,
        )
        yield from _iter_project_wbs_rows(
            project,
            prefix=section,
            packages=wp.sub_packages,
            depth=depth + 1,
        )


def iter_wbs_rows(
    roadmap: Roadmap,
    *,
    project_name: str | None = None,
) -> Iterator[list[str]]:
    """Yield CSV data rows for all matching projects in the roadmap.

    Args:
        roadmap: Loaded roadmap snapshot.
        project_name: When set, restrict export to this project name.

    Yields:
        One CSV row (list of string cells) per work package.
    """
    projects = sorted(roadmap.projects, key=lambda item: item.name)
    if project_name is not None:
        project = roadmap.project_by_name(project_name)
        if project is None:
            msg = f"project not found: {project_name!r}"
            raise ValueError(msg)
        projects = [project]
    for project in projects:
        yield from _iter_project_wbs_rows(project)


def write_wbs_csv(
    roadmap: Roadmap,
    output: TextIO,
    *,
    project_name: str | None = None,
) -> None:
    """Write a WBS CSV report to ``output``.

    Args:
        roadmap: Loaded roadmap snapshot.
        output: Writable text stream (file or stdout).
        project_name: When set, restrict export to this project name.
    """
    writer = csv.writer(output)
    writer.writerow(WBS_HEADERS)
    writer.writerows(iter_wbs_rows(roadmap, project_name=project_name))


def write_wbs_csv_file(
    roadmap: Roadmap,
    path: Path,
    *,
    project_name: str | None = None,
) -> None:
    """Write a WBS CSV report to ``path``.

    Args:
        roadmap: Loaded roadmap snapshot.
        path: Destination file path.
        project_name: When set, restrict export to this project name.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        write_wbs_csv(roadmap, handle, project_name=project_name)
