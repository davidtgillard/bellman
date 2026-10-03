"""Domain model for roadmap entities."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from bellman.errors import BellmanError


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
    unit: Literal["h", "d", "w"]


@dataclass(frozen=True, slots=True)
class UnknownEstimate:
    """Placeholder when duration has not been determined."""


UNKNOWN_ESTIMATE = UnknownEstimate()

Estimate = ThreePointEstimate | UnknownEstimate
"""Work-package duration: a full 3-point estimate or explicitly unknown."""

ATTRIBUTE_KINDS = ("initiative", "project", "work_package", "milestone", "goal")
"""Entity kinds an attribute may apply to (``applies_to`` tokens)."""

AttributeScalar = str | int | float | bool
"""JSON scalar usable as an attribute value or assignment payload field."""

AttributeValue = AttributeScalar | Mapping[str, AttributeScalar]
"""Assigned value: a scalar, or a flat object for open-value attributes."""

AttributeVersion = tuple[int, int]
"""Attribute contract version as ``(major, minor)``."""


def format_attribute_version(version: AttributeVersion) -> str:
    """Format an attribute version as ``x.y``.

    Args:
        version: ``(major, minor)`` pair.

    Returns:
        The dotted string, for example ``"1.2"``.
    """
    return f"{version[0]}.{version[1]}"


@dataclass(frozen=True, slots=True)
class AttributeAssignment:
    """One attribute assigned to an entity.

    Attributes:
        name: Attribute name (kebab-case).
        value: Assigned value; a token string for plain-set and keyed
            attributes, a scalar or flat object for open-value attributes.
        payload: Flat key/value data written on the assignment itself
            (checked against the definition's ``assignment_schema``).
        pinned_version: Contract version the assignment was written against
            (``name@x.y``), or ``None`` when unpinned.
    """

    name: str
    value: AttributeValue
    payload: Mapping[str, AttributeScalar] = field(default_factory=dict)
    pinned_version: AttributeVersion | None = None


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    """One ``attributes/{name}.jsonc`` definition.

    Attributes:
        name: Attribute name (kebab-case); equals the file stem.
        path: Path of the definition file (for error reporting).
        version: Contract version ``(major, minor)``.
        applies_to: Entity kinds that may carry the attribute.
        cardinality: ``"one"`` or ``"many"`` assignments per entity.
        required: When true, every entity of an applicable kind must be
            assigned the attribute.
        description: Optional one-line explanation.
        values: ``None`` for open-value attributes, a tuple of tokens for a
            plain set, or a mapping from token to entry data for keyed
            metadata.
        value_schema: JSON Schema for keyed entries, or for open values.
        assignment_schema: JSON Schema for assignment payload data.
    """

    name: str
    path: str
    version: AttributeVersion
    applies_to: tuple[str, ...]
    cardinality: Literal["one", "many"]
    required: bool = False
    description: str = ""
    values: tuple[str, ...] | Mapping[str, Mapping[str, Any]] | None = None
    value_schema: Mapping[str, Any] | bool | None = None
    assignment_schema: Mapping[str, Any] | bool | None = None

    @property
    def shape(self) -> Literal["set", "keyed", "open"]:
        """Definition shape: ``set``, ``keyed``, or ``open``."""
        if self.values is None:
            return "open"
        if isinstance(self.values, tuple):
            return "set"
        return "keyed"

    def allowed_values(self) -> tuple[str, ...] | None:
        """Return the legal value tokens, or ``None`` for open values.

        Returns:
            Tokens for plain-set and keyed attributes; ``None`` when any value
            matching ``value_schema`` is allowed.
        """
        if self.values is None:
            return None
        if isinstance(self.values, tuple):
            return self.values
        return tuple(self.values)


@dataclass(frozen=True, slots=True)
class AttributeCatalog:
    """Attribute definitions loaded from ``attributes/``.

    Attributes:
        definitions: Valid definitions keyed by attribute name.
        invalid_names: Names (file stems) of definition files that failed
            validation; assignments naming them are not reported again.
        problems: Errors found while checking definition files.
    """

    definitions: Mapping[str, AttributeDefinition] = field(default_factory=dict)
    invalid_names: frozenset[str] = frozenset()
    problems: tuple[BellmanError, ...] = ()

    def get(self, name: str) -> AttributeDefinition | None:
        """Return the definition for ``name``, or ``None`` when unknown.

        Args:
            name: Attribute name.

        Returns:
            The definition, or ``None``.
        """
        return self.definitions.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self.definitions

    def __iter__(self) -> Iterator[AttributeDefinition]:
        """Iterate definitions in name order."""
        for name in sorted(self.definitions):
            yield self.definitions[name]

    def __len__(self) -> int:
        return len(self.definitions)


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
    classifications: tuple[AttributeAssignment, ...] = ()


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
    title: str
    description: str
    notes: str = ""
    estimate: Estimate | None = None
    sub_packages: tuple[WorkPackage, ...] = ()
    dependencies: tuple[PrecedenceEdge, ...] = ()
    classifications: tuple[AttributeAssignment, ...] = ()


@dataclass(frozen=True, slots=True)
class Milestone:
    """Roadmap milestone with a target date."""

    name: str
    title: str
    path: str
    date: str
    description: str
    classifications: tuple[AttributeAssignment, ...] = ()


@dataclass(frozen=True, slots=True)
class Goal:
    """Outcome the roadmap contributes toward."""

    name: str
    title: str
    path: str
    description: str
    classifications: tuple[AttributeAssignment, ...] = ()


@dataclass(frozen=True, slots=True)
class Roadmap:
    """Loaded roadmap snapshot."""

    root: str
    initiatives: tuple[Initiative, ...] = ()
    projects: tuple[Project, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    goals: tuple[Goal, ...] = ()
    archived_initiatives: tuple[Initiative, ...] = ()
    attributes: AttributeCatalog = field(default_factory=AttributeCatalog)

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
        """Return live initiatives, projects, and unpromoted archived initiatives."""
        archived = [
            item
            for item in self.archived_initiatives
            if self.project_by_name(item.name) is None
        ]
        return [
            *self.initiatives,
            *self.projects,
            *archived,
        ]

    def work_package_slugs(self, project_name: str) -> set[str]:
        project = self.project_by_name(project_name)
        if project is None:
            return set()

        slugs: set[str] = set()

        def walk(packages: tuple[WorkPackage, ...]) -> None:
            for wp in packages:
                slugs.add(wp.slug)
                walk(wp.sub_packages)

        walk(project.work_packages)
        return slugs
