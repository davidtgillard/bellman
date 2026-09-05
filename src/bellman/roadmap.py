"""Load a roadmap directory into a :class:`Roadmap`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bellman import layout
from bellman.errors import BellmanError
from bellman.model import Goal, Initiative, Milestone, Project, Roadmap
from bellman.parse.goal import parse_goal
from bellman.parse.milestone import parse_milestone
from bellman.parse.work_scope import parse_work_scope


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Outcome of loading a roadmap for validation."""

    roadmap: Roadmap
    errors: tuple[BellmanError, ...]


def _append_parsed[T](
    path: Path,
    parse: Callable[[], T],
    errors: list[BellmanError],
    target: list[T],
) -> None:
    try:
        target.append(parse())
    except (ValueError, OSError) as exc:
        errors.append(BellmanError(str(path), str(exc)))


def _parse_archived_initiative(path: Path) -> Initiative:
    """Parse ``{name}.archived.md`` preserving the original initiative name."""
    name = path.name[: -len(layout.ARCHIVED_SUFFIX)]
    initiative = parse_work_scope(path, is_project=False, name=name)
    assert isinstance(initiative, Initiative)
    return initiative


def load_for_validation(root: Path) -> LoadResult:
    """Load roadmap entities from ``root``, collecting parse errors.

    Args:
        root: Roadmap root directory.

    Returns:
        Parsed roadmap plus any load errors encountered while reading files.
    """
    errors: list[BellmanError] = []
    initiatives: list[Initiative] = []
    archived: list[Initiative] = []
    projects: list[Project] = []
    milestones: list[Milestone] = []
    goals: list[Goal] = []

    init_dir = root / layout.INITIATIVES_DIR
    if init_dir.is_dir():
        for path in sorted(init_dir.glob("*.md")):
            if path.name.endswith(layout.ARCHIVED_SUFFIX):

                def parse_archived(p: Path = path) -> Initiative:
                    return _parse_archived_initiative(p)

                _append_parsed(path, parse_archived, errors, archived)
                continue

            def parse_initiative(p: Path = path) -> Initiative:
                scope = parse_work_scope(p, is_project=False)
                assert isinstance(scope, Initiative)
                return scope

            _append_parsed(path, parse_initiative, errors, initiatives)

    proj_dir = root / layout.PROJECTS_DIR
    if proj_dir.is_dir():
        for pdir in sorted(proj_dir.iterdir()):
            if not pdir.is_dir() or layout.is_archived_project_dir(pdir):
                continue
            md = layout.project_md_path(root, pdir.name)
            wp = layout.work_packages_path(root, pdir.name)

            def parse_project(
                project_md: Path = md,
                work_packages: Path = wp,
            ) -> Project:
                scope = parse_work_scope(
                    project_md,
                    is_project=True,
                    work_packages_path=work_packages,
                )
                assert isinstance(scope, Project)
                return scope

            _append_parsed(md, parse_project, errors, projects)

    ms_dir = root / layout.MILESTONES_DIR
    if ms_dir.is_dir():
        for path in sorted(ms_dir.glob("*.md")):

            def parse_milestone_file(p: Path = path) -> Milestone:
                return parse_milestone(p)

            _append_parsed(path, parse_milestone_file, errors, milestones)

    goal_dir = root / layout.GOALS_DIR
    if goal_dir.is_dir():
        for path in sorted(goal_dir.glob("*.md")):

            def parse_goal_file(p: Path = path) -> Goal:
                return parse_goal(p)

            _append_parsed(path, parse_goal_file, errors, goals)

    roadmap = Roadmap(
        root=str(root.resolve()),
        initiatives=tuple(initiatives),
        projects=tuple(projects),
        milestones=tuple(milestones),
        goals=tuple(goals),
        archived_initiatives=tuple(archived),
    )
    return LoadResult(roadmap=roadmap, errors=tuple(errors))


def load(root: Path) -> Roadmap:
    """Load all roadmap entities from ``root``.

    Raises:
        ValueError: When any entity file fails to parse.
        OSError: When a roadmap file cannot be read.
    """
    result = load_for_validation(root)
    if result.errors:
        first = result.errors[0]
        msg = first.message
        raise ValueError(msg)
    return result.roadmap
