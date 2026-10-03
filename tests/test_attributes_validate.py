"""Built-in validation of attribute assignments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from attr_support import (
    PRIORITY_JSONC,
    PROGRAM_JSONC,
    make_root,
    wp_block,
    wp_yaml,
    write_attribute,
    write_goal,
    write_initiative,
    write_milestone,
    write_project,
)
from pyfits.result import Ok
from typer.testing import CliRunner

from bellman.attributes.check import check_attributes
from bellman.cli import app
from bellman.report.status import compute_roadmap_status
from bellman.roadmap import load
from bellman.validate import validate_roadmap

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def _messages(root: Path) -> list[str]:
    return [e.message for e in validate_roadmap(load(root)).errors]


def _base(tmp_path: Path) -> Path:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_attribute(root, "program", PROGRAM_JSONC)
    return root


def _only(messages: list[str]) -> str:
    assert len(messages) == 1, messages
    return messages[0]


def test_example_roadmap_has_no_attribute_errors() -> None:
    assert check_attributes(load(EXAMPLES)) == []


def test_valid_assignments_pass(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1", "program@1.2: data-residency"])
    write_project(
        root,
        "beta",
        ["priority: P0", "program: platform-v2 [allocation: 0.5]"],
        work_packages=wp_yaml(
            wp_block("wp-one", "      program:\n        - value: platform-v2\n")
        ),
    )
    assert _messages(root) == []


def test_unknown_attribute(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1", "color: red"])
    message = _only(_messages(root))
    assert "initiative 'alpha'" in message
    assert "unknown attribute 'color'" in message


def test_attribute_does_not_apply_to_kind(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1"])
    write_goal(root, "g", ["priority: P1"])
    message = _only(_messages(root))
    assert "goal 'g'" in message
    assert "does not apply to goal (applies to: initiative, project)" in message


def test_plain_set_value_must_be_listed(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P9"])
    message = _only(_messages(root))
    assert "value 'P9' is not allowed for attribute 'priority'" in message
    assert "allowed: P0, P1, P2" in message


def test_keyed_value_must_be_a_key(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1", "program: nope"])
    message = _only(_messages(root))
    assert "value 'nope' is not allowed for attribute 'program'" in message


def test_mapping_value_is_rejected_for_fixed_values(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_project(
        root,
        "beta",
        ["priority: P1"],
        work_packages=wp_yaml(
            wp_block("wp-one", "      program:\n        value:\n          k: 1\n")
        ),
    )
    assert "not allowed for attribute 'program'" in _only(_messages(root))


def _open_attribute(root: Path, schema: dict[str, object]) -> None:
    write_attribute(
        root,
        "score",
        json.dumps(
            {
                "name": "score",
                "version": "1.0",
                "applies_to": ["initiative", "work_package"],
                "cardinality": "many",
                "value_schema": schema,
            }
        ),
    )


@pytest.mark.parametrize(
    ("schema", "value", "ok"),
    [
        ({"type": "integer", "maximum": 5}, "3", True),
        ({"type": "integer", "maximum": 5}, "9", False),
        ({"type": "integer"}, "abc", False),
        ({"type": "number"}, "1.5", True),
        ({"type": "number"}, "2", True),
        ({"type": "boolean"}, "true", True),
        ({"type": "boolean"}, "false", True),
        ({"type": "boolean"}, "yes", False),
        ({"type": "string", "pattern": "^a"}, "abc", True),
        ({"type": "string", "pattern": "^a"}, "bcd", False),
    ],
)
def test_open_values_are_coerced_and_checked(
    tmp_path: Path,
    schema: dict[str, object],
    value: str,
    ok: bool,
) -> None:
    root = make_root(tmp_path)
    _open_attribute(root, schema)
    write_initiative(root, "alpha", [f"score: {value}"])
    messages = _messages(root)
    if ok:
        assert messages == []
    else:
        assert "is not valid for attribute 'score'" in _only(messages)


def test_open_value_object_from_yaml(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    _open_attribute(
        root,
        {
            "type": "object",
            "required": ["low"],
            "properties": {"low": {"type": "number"}},
        },
    )
    write_project(
        root,
        "beta",
        work_packages=wp_yaml(
            wp_block("good", "      score:\n        value: {low: 1}\n"),
            wp_block("bad", "      score:\n        value: {high: 2}\n"),
        ),
    )
    message = _only(_messages(root))
    assert "work_package 'beta/bad'" in message
    assert "is not valid for attribute 'score'" in message


def test_assignment_payload_is_checked(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(
        root,
        "alpha",
        [
            "priority: P1",
            "program: platform-v2 [allocation: 2]",
            "program: data-residency [colour: red]",
        ],
    )
    messages = _messages(root)
    assert len(messages) == 2
    assert any("allocation: 2 is greater than the maximum" in m for m in messages)
    assert any("Additional properties" in m for m in messages)


def test_payload_without_assignment_schema_is_rejected(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1 [note: hi]"])
    message = _only(_messages(root))
    assert "does not accept assignment data" in message


@pytest.mark.parametrize(
    ("current", "pin", "expected"),
    [
        ("1.2", "1.2", None),
        ("1.2", "1.0", None),
        ("1.2", "1.1", None),
        ("2.0", "1.9", "pinned to an older major version; program is now 2.0"),
        ("2.3", "1.0", "pinned to an older major version; program is now 2.3"),
        ("1.2", "1.3", "newer than the definition (program is 1.2)"),
        ("1.2", "2.0", "newer than the definition (program is 1.2)"),
    ],
)
def test_version_pins(
    tmp_path: Path,
    current: str,
    pin: str,
    expected: str | None,
) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "program",
        PROGRAM_JSONC.replace('"version": "1.2"', f'"version": "{current}"'),
    )
    write_initiative(root, "alpha", [f"program@{pin}: platform-v2"])
    messages = _messages(root)
    if expected is None:
        assert messages == []
    else:
        message = _only(messages)
        assert f"program@{pin}" in message
        assert expected in message


def test_pin_error_says_to_review(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "program",
        PROGRAM_JSONC.replace('"version": "1.2"', '"version": "2.0"'),
    )
    write_initiative(root, "alpha", ["program@1.2: platform-v2"])
    assert "Review and update the pin." in _only(_messages(root))


def test_pins_in_work_package_yaml(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_project(
        root,
        "beta",
        ["priority: P1"],
        work_packages=wp_yaml(
            wp_block("wp-one", "      program@3.0: platform-v2\n"),
        ),
    )
    assert "newer than the definition" in _only(_messages(root))


def test_cardinality_one_rejects_two_assignments(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1", "priority: P2"])
    message = _only(_messages(root))
    assert "allows one assignment but has 2" in message


def test_cardinality_many_allows_several(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(
        root,
        "alpha",
        ["priority: P1", "program: platform-v2", "program: data-residency"],
    )
    assert _messages(root) == []


def test_duplicate_assignment_is_reported_once(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(
        root,
        "alpha",
        ["priority: P1", "program: platform-v2", "program: platform-v2"]
        + ["program: platform-v2"],
    )
    message = _only(_messages(root))
    assert "duplicate assignment program: platform-v2" in message


def test_duplicate_object_values_ignore_key_order(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    _open_attribute(root, {"type": "object"})
    write_project(
        root,
        "beta",
        work_packages=wp_yaml(
            wp_block(
                "dup",
                "      score:\n"
                "        - value: {a: 1, b: 2}\n"
                "        - value: {b: 2, a: 1}\n"
                "        - value: {a: 1, b: 3}\n",
            ),
        ),
    )
    message = _only(_messages(root))
    assert "duplicate assignment score" in message


def test_missing_required_attribute(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha")
    write_project(root, "beta", ["priority: P1"])
    write_milestone(root, "ga")  # kind not in applies_to: not required
    message = _only(_messages(root))
    assert "initiative 'alpha'" in message
    assert "missing required attribute 'priority'" in message


def test_required_many_needs_at_least_one(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "team",
        json.dumps(
            {
                "name": "team",
                "version": "1.0",
                "applies_to": ["project"],
                "cardinality": "many",
                "required": True,
                "values": ["red", "blue"],
            }
        ),
    )
    write_project(root, "beta")
    write_project(root, "gamma", ["team: red", "team: blue"])
    message = _only(_messages(root))
    assert "project 'beta'" in message
    assert "missing required attribute 'team'" in message


def test_required_applies_to_every_work_package(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "owner",
        json.dumps(
            {
                "name": "owner",
                "version": "1.0",
                "applies_to": ["work_package"],
                "cardinality": "one",
                "required": True,
                "values": ["ann", "bob"],
            }
        ),
    )
    nested = (
        "  - title: parent\n"
        "    description: Do it.\n"
        "    classifications:\n"
        "      owner: ann\n"
        "    sub_packages:\n"
        "      - title: child\n"
        "        description: Do it.\n"
        "        estimate: [1d, 2d, 3d]\n"
    )
    write_project(root, "beta", work_packages=wp_yaml(nested))
    message = _only(_messages(root))
    assert "work_package 'beta/child'" in message
    assert "missing required attribute 'owner'" in message


def test_required_checked_on_every_kind(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "risk",
        json.dumps(
            {
                "name": "risk",
                "version": "1.0",
                "applies_to": ["initiative", "project", "milestone", "goal"],
                "cardinality": "one",
                "required": True,
                "values": ["low", "high"],
            }
        ),
    )
    write_initiative(root, "i")
    write_project(root, "p")
    write_milestone(root, "m")
    write_goal(root, "g")
    kinds = sorted(m.split(" ")[0] for m in _messages(root))
    assert kinds == ["goal", "initiative", "milestone", "project"]


def test_archived_initiative_is_checked_until_promoted(tmp_path: Path) -> None:
    root = _base(tmp_path)
    archived = write_initiative(root, "old")
    archived.rename(archived.with_name("old.archived.md"))
    assert any("initiative 'old'" in m for m in _messages(root))
    write_project(root, "old", ["priority: P1"])
    assert _messages(root) == []


def test_invalid_definition_is_reported_and_suppresses_noise(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "priority",
        json.dumps(
            {
                "name": "priority",
                "version": "1",
                "applies_to": ["initiative"],
                "cardinality": "one",
                "required": True,
                "values": ["P0"],
            }
        ),
    )
    write_initiative(root, "alpha", ["priority: P0"])
    write_initiative(root, "beta")
    message = _only(_messages(root))
    assert message.startswith("version:")


def test_syntax_error_definition_is_load_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", "{ not json")
    write_initiative(root, "alpha", ["priority: P0"])
    result = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert result.exit_code == 1
    assert "invalid attribute definition" in result.output
    assert "unknown attribute" not in result.output


def test_cli_validate_reports_attribute_errors(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P9"])
    result = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert result.exit_code == 1
    assert "value 'P9' is not allowed" in result.output


def test_cli_validate_passes_for_valid_roadmap(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P1"])
    result = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert result.exit_code == 0, result.output
    assert "Markdown validation passed" in result.output


def test_status_surfaces_attribute_errors(tmp_path: Path) -> None:
    root = _base(tmp_path)
    write_initiative(root, "alpha", ["priority: P9"])
    result = compute_roadmap_status(root, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    issues = [i for e in status.entities for i in e.issues]
    assert any("value 'P9' is not allowed" in i for i in issues)


def test_status_reports_definition_problems_globally(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "bad",
        json.dumps({"name": "bad", "version": "x", "applies_to": ["goal"]}),
    )
    result = compute_roadmap_status(root, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    assert any("version:" in issue for issue in status.global_issues)
