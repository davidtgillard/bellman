"""Load the shipped attribute-definition JSON Schema."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

__all__ = [
    "ATTRIBUTE_DEFINITION_SCHEMA_VERSION",
    "definition_validator",
    "load_attribute_definition_schema",
]

ATTRIBUTE_DEFINITION_SCHEMA_VERSION = "1.0"
"""Version of the shipped attribute-definition schema document."""


def load_attribute_definition_schema() -> dict[str, Any]:
    """Return the JSON Schema for ``attributes/{name}.jsonc`` files.

    Returns:
        Parsed JSON Schema document whose ``x-schema-version`` matches
        :data:`ATTRIBUTE_DEFINITION_SCHEMA_VERSION`.

    Raises:
        FileNotFoundError: When the schema resource is missing from the
            package.
        ValueError: When the schema file is not a valid JSON object.
    """
    version = ATTRIBUTE_DEFINITION_SCHEMA_VERSION
    path = files("bellman.attributes.schemas").joinpath(
        f"attribute-definition-{version}.json"
    )
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        msg = f"attribute definition schema {version} is not installed"
        raise FileNotFoundError(msg) from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"attribute definition schema {version} is not valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(document, dict):
        msg = f"attribute definition schema {version} must be a JSON object"
        raise ValueError(msg)
    return document


@cache
def definition_validator() -> Draft202012Validator:
    """Return a cached validator for attribute definition documents.

    Returns:
        Draft 2020-12 validator built from the shipped schema.

    Raises:
        FileNotFoundError: When the schema resource is missing.
        ValueError: When the schema file is invalid.
    """
    return Draft202012Validator(load_attribute_definition_schema())
