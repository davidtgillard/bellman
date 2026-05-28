"""Load a roadmap directory into a :class:`Roadmap`."""

from __future__ import annotations

from pathlib import Path

from snark import layout
from snark.model import Goal, Initiative, Milestone, Project, Roadmap
from snark.parse.goal import parse_goal
from snark.parse.milestone import parse_milestone
from snark.parse.work_scope import parse_work_scope


def _parse_archived_initiative(path: Path) -> Initiative:
    """Parse ``{name}.archived.md`` preserving the original initiative name."""
    initiative = parse_work_scope(path, is_project=False)
    assert isinstance(initiative, Initiative)
    name = path.name[: -len(layout.ARCHIVED_SUFFIX)]
    return Initiative(
        name=name,
        title=initiative.title,
        path=initiative.path,
        introduction=initiative.introduction,
        motivation=initiative.motivation,
        detailed_description=initiative.detailed_description,
        dependencies=initiative.dependencies,
    )


def load(root: Path) -> Roadmap:
    """Load all roadmap entities from ``root``."""
    initiatives: list[Initiative] = []
    archived: list[Initiative] = []
    projects: list[Project] = []
    milestones: list[Milestone] = []
    goals: list[Goal] = []

    init_dir = root / layout.INITIATIVES_DIR
    if init_dir.is_dir():
        for path in sorted(init_dir.glob("*.md")):
            if path.name.endswith(layout.ARCHIVED_SUFFIX):
                archived.append(_parse_archived_initiative(path))
                continue
            initiatives.append(
                parse_work_scope(path, is_project=False)  # type: ignore[arg-type]
            )

    proj_dir = root / layout.PROJECTS_DIR
    if proj_dir.is_dir():
        for pdir in sorted(proj_dir.iterdir()):
            if not pdir.is_dir():
                continue
            md = layout.project_md_path(root, pdir.name)
            wp = layout.work_packages_path(root, pdir.name)
            projects.append(
                parse_work_scope(md, is_project=True, work_packages_path=wp)
            )

    ms_dir = root / layout.MILESTONES_DIR
    if ms_dir.is_dir():
        for path in sorted(ms_dir.glob("*.md")):
            milestones.append(parse_milestone(path))

    goal_dir = root / layout.GOALS_DIR
    if goal_dir.is_dir():
        for path in sorted(goal_dir.glob("*.md")):
            goals.append(parse_goal(path))

    return Roadmap(
        root=str(root.resolve()),
        initiatives=tuple(initiatives),
        projects=tuple(projects),
        milestones=tuple(milestones),
        goals=tuple(goals),
        archived_initiatives=tuple(archived),
    )
