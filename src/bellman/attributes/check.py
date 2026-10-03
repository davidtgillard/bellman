"""Built-in validation of attribute assignments against definitions."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from bellman.attributes.entities import EntityRef, iter_entities
from bellman.errors import BellmanError
from bellman.model import (
    AttributeAssignment,
    AttributeDefinition,
    Roadmap,
    format_attribute_version,
)

__all__ = [
    "AttributeCheck",
    "check_attributes",
    "check_attributes_detailed",
    "errors_for_attributes",
]

_INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
_FLOAT_RE = re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+([eE][+-]?[0-9]+)?$")


def _candidates(value: Any) -> list[Any]:
    """Typed readings of a value; markdown values arrive as strings."""
    if isinstance(value, Mapping):
        return [dict(value)]
    if not isinstance(value, str):
        return [value]
    out: list[Any] = [value]
    if value in {"true", "false"}:
        out.append(value == "true")
    if _INT_RE.fullmatch(value):
        out.append(int(value))
    if _INT_RE.fullmatch(value) or _FLOAT_RE.fullmatch(value):
        out.append(float(value))
    return out


def _value_problem(defn: AttributeDefinition, value: Any) -> str | None:
    """Return a message when ``value`` is not legal for ``defn``."""
    allowed = defn.allowed_values()
    if allowed is not None:
        if isinstance(value, Mapping) or str(value) not in allowed:
            shown = ", ".join(allowed)
            return (
                f"value {value!r} is not allowed for attribute {defn.name!r} "
                f"(allowed: {shown})"
            )
        return None
    # Open-value definitions always carry a value_schema (the shipped schema
    # requires it); ``True`` accepts any value if one is ever missing.
    schema = defn.value_schema if defn.value_schema is not None else True
    validator = Draft202012Validator(schema)
    for candidate in _candidates(value):
        if validator.is_valid(candidate):
            return None
    error = best_match(validator.iter_errors(_candidates(value)[0]))
    detail = error.message if error is not None else "does not match value_schema"
    return f"value {value!r} is not valid for attribute {defn.name!r}: {detail}"


def _payload_problems(
    defn: AttributeDefinition,
    assignment: AttributeAssignment,
) -> list[str]:
    payload = dict(assignment.payload)
    if not payload:
        return []
    if defn.assignment_schema is None:
        return [
            f"attribute {defn.name!r} does not accept assignment data "
            f"(no assignment_schema); got {sorted(payload)}"
        ]
    validator = Draft202012Validator(defn.assignment_schema)
    problems: list[str] = []
    for error in sorted(
        validator.iter_errors(payload),
        key=lambda err: [str(p) for p in err.absolute_path],
    ):
        where = "/".join(str(p) for p in error.absolute_path)
        prefix = f"{where}: " if where else ""
        problems.append(
            f"assignment data for {defn.name!r} is invalid: {prefix}{error.message}"
        )
    return problems


def _canonical(value: object) -> str:
    """Return a key that is equal for equal values, whatever the key order."""
    return json.dumps(value, sort_keys=True, default=repr)


def _pin_problem(
    defn: AttributeDefinition, assignment: AttributeAssignment
) -> str | None:
    pin = assignment.pinned_version
    if pin is None:
        return None
    current = defn.version
    pinned_text = f"{defn.name}@{format_attribute_version(pin)}"
    current_text = format_attribute_version(current)
    if pin[0] < current[0]:
        return (
            f"{pinned_text} is pinned to an older major version; "
            f"{defn.name} is now {current_text}. Review and update the pin."
        )
    if pin > current:
        return (
            f"{pinned_text} is newer than the definition "
            f"({defn.name} is {current_text})"
        )
    return None


def errors_for_attributes(
    entity: EntityRef,
    roadmap: Roadmap,
    failed: set[str] | None = None,
) -> list[BellmanError]:
    """Check one entity's assignments against the catalog.

    Args:
        entity: Entity and its assignments.
        roadmap: Loaded roadmap (provides the attribute catalog).
        failed: When given, receives the name of every attribute that produced
            an error (used to decide which custom validators may run).

    Returns:
        Errors for unknown or inapplicable attributes, illegal values, bad
        payloads, version pins, cardinality, duplicates, and missing required
        assignments.
    """
    catalog = roadmap.attributes
    errors: list[BellmanError] = []

    def error(attribute: str, message: str) -> None:
        if failed is not None:
            failed.add(attribute)
        errors.append(
            BellmanError(entity.path, f"{entity.kind} {entity.name!r}: {message}")
        )

    seen: Counter[tuple[str, str]] = Counter()
    per_name: Counter[str] = Counter()
    for assignment in entity.classifications:
        if assignment.name in catalog.invalid_names:
            continue
        defn = catalog.get(assignment.name)
        if defn is None:
            error(assignment.name, f"unknown attribute {assignment.name!r}")
            continue
        per_name[defn.name] += 1
        if entity.kind not in defn.applies_to:
            applies = ", ".join(defn.applies_to)
            error(
                defn.name,
                f"attribute {defn.name!r} does not apply to {entity.kind} "
                f"(applies to: {applies})",
            )
            continue
        pin_problem = _pin_problem(defn, assignment)
        if pin_problem is not None:
            error(defn.name, pin_problem)
        value_problem = _value_problem(defn, assignment.value)
        if value_problem is not None:
            error(defn.name, value_problem)
        for problem in _payload_problems(defn, assignment):
            error(defn.name, problem)
        key = (defn.name, _canonical(assignment.value))
        seen[key] += 1
        if seen[key] == 2:
            error(defn.name, f"duplicate assignment {defn.name}: {assignment.value}")

    for name, count in per_name.items():
        defn = catalog.definitions[name]
        if defn.cardinality == "one" and count > 1:
            error(name, f"attribute {name!r} allows one assignment but has {count}")

    for defn in catalog:
        if (
            defn.required
            and entity.kind in defn.applies_to
            and per_name[defn.name] == 0
        ):
            error(defn.name, f"missing required attribute {defn.name!r}")
    return errors


@dataclass(frozen=True, slots=True)
class AttributeCheck:
    """Result of checking all attribute definitions and assignments.

    Attributes:
        errors: Definition problems followed by per-entity errors.
        failed_attributes: Names of attributes involved in any error,
            including definitions that failed validation.
    """

    errors: tuple[BellmanError, ...]
    failed_attributes: frozenset[str]


def check_attributes_detailed(roadmap: Roadmap) -> AttributeCheck:
    """Validate attribute definitions and every entity's assignments.

    Args:
        roadmap: Loaded roadmap.

    Returns:
        The errors and the set of attribute names that had errors.
    """
    errors: list[BellmanError] = list(roadmap.attributes.problems)
    failed: set[str] = set(roadmap.attributes.invalid_names)
    for entity in iter_entities(roadmap):
        errors.extend(errors_for_attributes(entity, roadmap, failed))
    return AttributeCheck(tuple(errors), frozenset(failed))


def check_attributes(roadmap: Roadmap) -> list[BellmanError]:
    """Validate attribute definitions and every entity's assignments.

    Args:
        roadmap: Loaded roadmap.

    Returns:
        Definition problems from the catalog followed by per-entity errors.
    """
    return list(check_attributes_detailed(roadmap).errors)
