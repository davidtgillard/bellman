"""Attribute definition schema and catalog loading tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from attr_support import (
    BUDGET_JSONC,
    PRIORITY_JSONC,
    PROGRAM_JSONC,
    make_root,
    write_attribute,
)
from jsonschema import Draft202012Validator

from bellman.attributes import (
    ATTRIBUTE_DEFINITION_SCHEMA_VERSION,
    load_attribute_catalog,
    load_attribute_definition_schema,
)
from bellman.roadmap import load, load_for_validation

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def _valid(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": "priority",
        "version": "1.0",
        "applies_to": ["project"],
        "cardinality": "one",
        "values": ["P0", "P1"],
    }
    doc.update(overrides)
    return doc


def _errors(doc: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_attribute_definition_schema())
    return [e.message for e in validator.iter_errors(doc)]


def test_schema_document_is_valid_and_versioned() -> None:
    schema = load_attribute_definition_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["x-schema-version"] == ATTRIBUTE_DEFINITION_SCHEMA_VERSION


@pytest.mark.parametrize(
    "doc",
    [
        _valid(),
        _valid(values={"a1": {}, "b.2": {"x": 1}}),
        _valid(
            values=None,
            value_schema={"type": "number"},
        ),
        _valid(description="d", required=True, cardinality="many"),
        _valid(**{"$schema": "https://example.com/s.json"}),
        _valid(applies_to=["initiative", "work_package", "milestone"]),
    ],
)
def test_schema_accepts_valid_documents(doc: dict[str, Any]) -> None:
    if doc.get("values") is None:
        doc = {k: v for k, v in doc.items() if k != "values"}
    assert _errors(doc) == []


@pytest.mark.parametrize(
    ("doc", "fragment"),
    [
        (_valid(aplies_to=["project"]), "Additional properties"),
        (_valid(version="1"), "does not match"),
        (_valid(version="01.0"), "does not match"),
        (_valid(version="1.0.0"), "does not match"),
        (_valid(cardinality="two"), "is not one of"),
        (_valid(applies_to=[]), "non-empty"),
        (_valid(applies_to=["project", "project"]), "non-unique"),
        (_valid(applies_to=["team"]), "is not one of"),
        (_valid(name="Bad_Name"), "does not match"),
        (_valid(required="yes"), "is not of type"),
        (_valid(values=[]), "valid under any of the given schemas"),
        (_valid(values=["P0", "P0"]), "valid under any of the given schemas"),
        (_valid(values=["has space"]), "valid under any of the given schemas"),
        (_valid(values={"bad key": {}}), "valid under any of the given schemas"),
        (_valid(values={"ok": 1}), "valid under any of the given schemas"),
        (_valid(value_schema={"type": "number"}), "should not be valid"),
    ],
)
def test_schema_rejects_invalid_documents(
    doc: dict[str, Any],
    fragment: str,
) -> None:
    errors = _errors(doc)
    assert errors, "expected a schema violation"
    assert any(fragment in message for message in errors), errors


@pytest.mark.parametrize("missing", ["name", "version", "applies_to", "cardinality"])
def test_schema_requires_core_fields(missing: str) -> None:
    doc = _valid()
    del doc[missing]
    assert any("required property" in m for m in _errors(doc))


def test_open_value_requires_value_schema() -> None:
    doc = _valid()
    del doc["values"]
    assert any("value_schema" in m for m in _errors(doc))


def test_catalog_loads_all_shapes(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_attribute(root, "program", PROGRAM_JSONC)
    write_attribute(root, "budget", BUDGET_JSONC)
    catalog, errors = load_attribute_catalog(root)
    assert errors == ()
    assert catalog.problems == ()
    assert [d.name for d in catalog] == ["budget", "priority", "program"]
    assert len(catalog) == 3
    assert "priority" in catalog
    assert "nope" not in catalog
    assert catalog.get("nope") is None

    priority = catalog.get("priority")
    assert priority is not None
    assert priority.shape == "set"
    assert priority.version == (1, 0)
    assert priority.required is True
    assert priority.allowed_values() == ("P0", "P1", "P2")

    program = catalog.get("program")
    assert program is not None
    assert program.shape == "keyed"
    assert program.version == (1, 2)
    assert program.required is False
    assert program.allowed_values() == ("platform-v2", "data-residency")

    budget = catalog.get("budget")
    assert budget is not None
    assert budget.shape == "open"
    assert budget.allowed_values() is None


def test_missing_attributes_directory_is_empty_catalog(tmp_path: Path) -> None:
    catalog, errors = load_attribute_catalog(tmp_path)
    assert len(catalog) == 0
    assert errors == ()
    assert catalog.problems == ()


def test_non_jsonc_files_are_ignored(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "attributes" / "notes.md").write_text("hello", encoding="utf-8")
    (root / "attributes" / "old.json").write_text("{", encoding="utf-8")
    catalog, errors = load_attribute_catalog(root)
    assert len(catalog) == 0
    assert errors == ()


def test_syntax_error_is_a_load_error_with_line(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "broken", '{\n  "name": oops\n}\n')
    catalog, errors = load_attribute_catalog(root)
    assert len(errors) == 1
    assert errors[0].line == 2
    assert "invalid attribute definition" in errors[0].message
    assert "broken" in catalog.invalid_names
    with pytest.raises(ValueError, match="invalid attribute definition"):
        load(root)
    assert load_for_validation(root).errors


def test_unreadable_definition_is_a_load_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    path = write_attribute(root, "binary", "")
    path.write_bytes(b"\xff\xfe\x00")
    _catalog, errors = load_attribute_catalog(root)
    assert len(errors) == 1
    assert errors[0].line is None


def test_schema_violations_are_catalog_problems(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "bad",
        json.dumps(
            {"name": "bad", "version": "1", "applies_to": [], "cardinality": "two"}
        ),
    )
    catalog, errors = load_attribute_catalog(root)
    assert errors == ()
    assert len(catalog) == 0
    assert "bad" in catalog.invalid_names
    messages = [p.message for p in catalog.problems]
    assert any(m.startswith("version:") for m in messages)
    assert any(m.startswith("applies_to:") for m in messages)
    assert any(m.startswith("cardinality:") for m in messages)


def test_non_object_document_is_a_problem(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "list", "[1, 2]")
    catalog, errors = load_attribute_catalog(root)
    assert errors == ()
    assert [p.message for p in catalog.problems] == [
        "(root): definition must be a JSON object"
    ]
    assert "list" in catalog.invalid_names


def test_name_must_match_file_stem(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "other", PRIORITY_JSONC)
    catalog, _ = load_attribute_catalog(root)
    assert len(catalog) == 0
    assert catalog.invalid_names == frozenset({"other", "priority"})
    assert "must match the file name (other.jsonc)" in catalog.problems[0].message


def test_second_file_claiming_an_existing_name_is_rejected(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "a-priority", PRIORITY_JSONC)
    write_attribute(root, "priority", PRIORITY_JSONC)
    catalog, _ = load_attribute_catalog(root)
    assert [d.name for d in catalog] == ["priority"]
    assert any("(a-priority.jsonc)" in p.message for p in catalog.problems)


def test_invalid_embedded_schemas_are_reported(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "weird",
        json.dumps(
            {
                "name": "weird",
                "version": "1.0",
                "applies_to": ["project"],
                "cardinality": "one",
                "values": {"a": {"x": 1}},
                "value_schema": {"type": "not-a-type"},
                "assignment_schema": {"type": 12},
            }
        ),
    )
    catalog, _ = load_attribute_catalog(root)
    messages = [p.message for p in catalog.problems]
    assert any(m.startswith("value_schema: not a valid JSON Schema") for m in messages)
    assert any(
        m.startswith("assignment_schema: not a valid JSON Schema") for m in messages
    )
    assert not any(m.startswith("values/") for m in messages)


def test_keyed_entries_are_checked_against_value_schema(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "program",
        json.dumps(
            {
                "name": "program",
                "version": "1.0",
                "applies_to": ["project"],
                "cardinality": "many",
                "values": {
                    "good": {"title": "Good"},
                    "bad": {"title": 3, "probability": 7},
                    "missing": {},
                },
                "value_schema": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {
                        "title": {"type": "string"},
                        "probability": {"type": "number", "maximum": 1},
                    },
                },
            }
        ),
    )
    catalog, _ = load_attribute_catalog(root)
    messages = sorted(p.message for p in catalog.problems)
    assert any(m.startswith("values/bad/title:") for m in messages)
    assert any(m.startswith("values/bad/probability:") for m in messages)
    assert any(m.startswith("values/missing:") for m in messages)
    assert not any(m.startswith("values/good") for m in messages)
    assert len(catalog) == 0


def test_boolean_schemas_are_accepted(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "anything",
        json.dumps(
            {
                "name": "anything",
                "version": "0.1",
                "applies_to": ["milestone"],
                "cardinality": "many",
                "value_schema": True,
                "assignment_schema": False,
            }
        ),
    )
    catalog, _ = load_attribute_catalog(root)
    assert catalog.problems == ()
    assert catalog.get("anything") is not None


def test_example_definitions_load_cleanly() -> None:
    catalog, errors = load_attribute_catalog(EXAMPLES)
    assert errors == ()
    assert catalog.problems == ()
    assert [d.name for d in catalog] == ["goal", "priority", "program"]


def test_load_schema_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Missing:
        def joinpath(self, _name: str) -> _Missing:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            raise FileNotFoundError("gone")

    monkeypatch.setattr("bellman.attributes.schema.files", lambda _name: _Missing())
    with pytest.raises(FileNotFoundError, match="not installed"):
        load_attribute_definition_schema()


def test_load_schema_not_object(monkeypatch: pytest.MonkeyPatch) -> None:
    class _List:
        def joinpath(self, _name: str) -> _List:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            return "[1, 2]"

    monkeypatch.setattr("bellman.attributes.schema.files", lambda _name: _List())
    with pytest.raises(ValueError, match="JSON object"):
        load_attribute_definition_schema()


def test_load_schema_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Bad:
        def joinpath(self, _name: str) -> _Bad:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            return "{not json"

    monkeypatch.setattr("bellman.attributes.schema.files", lambda _name: _Bad())
    with pytest.raises(ValueError, match="not valid JSON"):
        load_attribute_definition_schema()
