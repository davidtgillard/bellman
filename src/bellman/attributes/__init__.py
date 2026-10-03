"""Roadmap attributes: definitions, assignments, and validation."""

from bellman.attributes.definition import load_attribute_catalog
from bellman.attributes.jsonc import loads_jsonc, strip_jsonc
from bellman.attributes.schema import (
    ATTRIBUTE_DEFINITION_SCHEMA_VERSION,
    definition_validator,
    load_attribute_definition_schema,
)

__all__ = [
    "ATTRIBUTE_DEFINITION_SCHEMA_VERSION",
    "definition_validator",
    "load_attribute_catalog",
    "load_attribute_definition_schema",
    "loads_jsonc",
    "strip_jsonc",
]
