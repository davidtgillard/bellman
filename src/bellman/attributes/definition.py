"""Load ``attributes/*.jsonc`` definition files into an :class:`AttributeCatalog`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError, best_match

from bellman import layout
from bellman.attributes.jsonc import loads_jsonc
from bellman.attributes.schema import definition_validator
from bellman.errors import BellmanError
from bellman.model import AttributeCatalog, AttributeDefinition
from bellman.parse.classifications import parse_version

__all__ = ["DEFINITION_SUFFIX", "load_attribute_catalog"]

DEFINITION_SUFFIX = ".jsonc"
"""File suffix of attribute definition files."""


def _location(error: ValidationError) -> str:
    parts = [str(part) for part in error.absolute_path]
    return "/".join(parts) if parts else "(root)"


def _schema_problems(doc: Any) -> list[str]:
    """Return messages for violations of the shipped definition schema."""
    if not isinstance(doc, dict):
        return ["(root): definition must be a JSON object"]
    problems: list[str] = []
    errors = sorted(
        definition_validator().iter_errors(doc),
        key=lambda err: [str(p) for p in err.absolute_path],
    )
    for error in errors:
        chosen = error
        if error.validator in {"oneOf", "anyOf"} and error.context:
            chosen = best_match(error.context) or error
        problems.append(f"{_location(error)}: {chosen.message}")
    return problems


def _embedded_schema_problems(doc: dict[str, Any]) -> list[str]:
    """Check embedded schemas and keyed entries (needs a schema-valid ``doc``)."""
    problems: list[str] = []
    schema_ok: dict[str, bool] = {}
    for key in ("value_schema", "assignment_schema"):
        if key not in doc:
            continue
        try:
            Draft202012Validator.check_schema(doc[key])
        except SchemaError as exc:
            problems.append(f"{key}: not a valid JSON Schema: {exc.message}")
            schema_ok[key] = False
        else:
            schema_ok[key] = True
    values = doc.get("values")
    if isinstance(values, dict) and schema_ok.get("value_schema"):
        validator = Draft202012Validator(doc["value_schema"])
        for token, entry in values.items():
            for error in sorted(
                validator.iter_errors(entry),
                key=lambda err: [str(p) for p in err.absolute_path],
            ):
                inner = "/".join(str(p) for p in error.absolute_path)
                where = f"values/{token}" + (f"/{inner}" if inner else "")
                problems.append(f"{where}: {error.message}")
    return problems


def _build_definition(path: Path, doc: dict[str, Any]) -> AttributeDefinition:
    raw_values = doc.get("values")
    values: tuple[str, ...] | dict[str, dict[str, Any]] | None
    if isinstance(raw_values, list):
        values = tuple(raw_values)
    elif isinstance(raw_values, dict):
        values = {token: dict(entry) for token, entry in raw_values.items()}
    else:
        values = None
    return AttributeDefinition(
        name=doc["name"],
        path=str(path),
        version=parse_version(doc["version"]),
        applies_to=tuple(doc["applies_to"]),
        cardinality=doc["cardinality"],
        required=bool(doc.get("required", False)),
        description=str(doc.get("description", "")),
        values=values,
        value_schema=doc.get("value_schema"),
        assignment_schema=doc.get("assignment_schema"),
    )


def load_attribute_catalog(
    root: Path,
) -> tuple[AttributeCatalog, tuple[BellmanError, ...]]:
    """Load every ``attributes/*.jsonc`` file under ``root``.

    A missing ``attributes/`` directory yields an empty catalog. Files whose
    JSONC cannot be read or parsed are returned as load errors. Files that parse
    but violate the definition schema (or the follow-up checks) are recorded in
    :attr:`AttributeCatalog.problems` and left out of the definitions, so
    ``bellman validate`` can report them.

    Args:
        root: Roadmap root directory.

    Returns:
        The catalog and the load errors (syntax or I/O failures).
    """
    directory = root / layout.ATTRIBUTES_DIR
    definitions: dict[str, AttributeDefinition] = {}
    invalid: set[str] = set()
    problems: list[BellmanError] = []
    load_errors: list[BellmanError] = []

    if not directory.is_dir():
        return AttributeCatalog(), ()

    for path in sorted(directory.glob(f"*{DEFINITION_SUFFIX}")):
        stem = path.name.removesuffix(DEFINITION_SUFFIX)
        try:
            doc = loads_jsonc(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            line = exc.lineno if isinstance(exc, json.JSONDecodeError) else None
            load_errors.append(
                BellmanError(str(path), f"invalid attribute definition: {exc}", line)
            )
            invalid.add(stem)
            continue

        messages = _schema_problems(doc)
        if not messages and isinstance(doc, dict):
            name = doc["name"]
            # name == file stem also guarantees no two files define one name.
            if name != stem:
                messages.append(
                    f"name: {name!r} must match the file name "
                    f"({stem}{DEFINITION_SUFFIX})"
                )
            messages.extend(_embedded_schema_problems(doc))
        if messages:
            invalid.add(stem)
            if isinstance(doc, dict) and isinstance(doc.get("name"), str):
                invalid.add(doc["name"])
            problems.extend(BellmanError(str(path), msg) for msg in messages)
            continue

        definition = _build_definition(path, doc)
        definitions[definition.name] = definition

    catalog = AttributeCatalog(
        definitions=definitions,
        invalid_names=frozenset(invalid),
        problems=tuple(problems),
    )
    return catalog, tuple(load_errors)
