"""Domain model for roadmap entities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class RelationType(StrEnum):
    """Precedence relation between activities."""

    FF = "FF"
    FS = "FS"
    SF = "SF"
    SS = "SS"


class Hardness(StrEnum):
    """Constraint strength on a precedence edge."""

    MANDATORY = "Mandatory"
    DISCRETIONARY = "Discretionary"
    OPTIONAL = "Optional"


@dataclass(frozen=True, slots=True)
class PrecedenceEdge:
    """Logical precedence from predecessor to dependent."""

    predecessor: str
    successor: str
    relation: RelationType
    hardness: Hardness


@dataclass(frozen=True, slots=True)
class ThreePointEstimate:
    """Optimistic / likely / pessimistic duration estimate."""

    optimistic: float
    most_likely: float
    pessimistic: float
    unit: Literal["days", "weeks"]


@dataclass(frozen=True, slots=True)
class WorkScope:
    """Shared fields for initiatives and projects."""

    name: str
    title: str
    path: str
    introduction: str
    motivation: str
    detailed_description: str
    dependencies: tuple[PrecedenceEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class Initiative(WorkScope):
    """Portfolio-level scope that may become a project."""


@dataclass(frozen=True, slots=True)
class Project(WorkScope):
    """Committed scope with success criteria and work packages."""

    criteria_for_success: str = ""
    work_packages: tuple[WorkPackage, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkPackage:
    """Decomposable unit of work within a project."""

    slug: str
    description: str
    estimate: ThreePointEstimate | None
    children: tuple[WorkPackage, ...] = ()
    dependencies: tuple[PrecedenceEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class Milestone:
    """Roadmap milestone with a target date."""

    name: str
    title: str
    path: str
    date: str
    description: str


@dataclass(frozen=True, slots=True)
class Goal:
    """Outcome the roadmap contributes toward."""

    name: str
    title: str
    path: str
    description: str


@dataclass(frozen=True, slots=True)
class Roadmap:
    """Loaded roadmap snapshot."""

    root: str
    initiatives: tuple[Initiative, ...] = ()
    projects: tuple[Project, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    goals: tuple[Goal, ...] = ()
    archived_initiatives: tuple[Initiative, ...] = ()

    def initiative_by_name(self, name: str) -> Initiative | None:
        for item in self.initiatives:
            if item.name == name:
                return item
        return None

    def project_by_name(self, name: str) -> Project | None:
        for item in self.projects:
            if item.name == name:
                return item
        return None

    def milestone_by_name(self, name: str) -> Milestone | None:
        for item in self.milestones:
            if item.name == name:
                return item
        return None

    def goal_by_name(self, name: str) -> Goal | None:
        for item in self.goals:
            if item.name == name:
                return item
        return None

    def all_work_scopes(self) -> list[Initiative | Project]:
        return [
            *self.initiatives,
            *self.projects,
            *self.archived_initiatives,
        ]

    def work_package_slugs(self, project_name: str) -> set[str]:
        project = self.project_by_name(project_name)
        if project is None:
            return set()

        slugs: set[str] = set()

        def walk(packages: tuple[WorkPackage, ...]) -> None:
            for wp in packages:
                slugs.add(wp.slug)
                walk(wp.children)

        walk(project.work_packages)
        return slugs
