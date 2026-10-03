"""Custom validator protocol and registration dataclass."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from bellman.attributes.entities import EntityRef, iter_entities
from bellman.errors import BellmanError, BellmanWarning
from bellman.model import AttributeCatalog, AttributeDefinition, Roadmap

__all__ = ["BellmanValidator", "ValidationContext", "ValidatorRun"]


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Read-only view of the roadmap handed to custom validators.

    Validators must not mutate the roadmap or write files; that is documented
    but not enforced.

    Attributes:
        roadmap: Loaded roadmap snapshot.
        root: Roadmap root directory.
    """

    roadmap: Roadmap
    root: Path

    @property
    def catalog(self) -> AttributeCatalog:
        """Attribute definitions loaded from ``attributes/``."""
        return self.roadmap.attributes

    def definition(self, name: str) -> AttributeDefinition | None:
        """Return the definition of attribute ``name``.

        Args:
            name: Attribute name.

        Returns:
            The definition, or ``None`` when no valid definition exists.
        """
        return self.roadmap.attributes.get(name)

    def entities(self, kind: str | None = None) -> Iterator[EntityRef]:
        """Iterate entities that can carry attribute assignments.

        Args:
            kind: When set, yield only entities of this kind (``initiative``,
                ``project``, ``work_package``, or ``milestone``).

        Yields:
            One :class:`~bellman.attributes.entities.EntityRef` per entity.
        """
        return iter_entities(self.roadmap, kind)


ValidatorRun = Callable[[ValidationContext], Iterable[BellmanError | BellmanWarning]]
"""Validator entry: context in, errors and warnings out."""


@dataclass(frozen=True, slots=True)
class BellmanValidator:
    """Repo-local validator registered under ``validator/{name}/``.

    Attributes:
        name: Validator name; must equal its directory name (kebab-case).
        summary: One-line description of the rule.
        attributes: Attribute names the validator reads. One name is a
            per-attribute rule; several is an invariant between attributes.
            The validator runs only when none of these attributes has a
            built-in validation error.
        run: Function returning errors and warnings for the roadmap.
    """

    name: str
    summary: str
    attributes: tuple[str, ...]
    run: ValidatorRun
