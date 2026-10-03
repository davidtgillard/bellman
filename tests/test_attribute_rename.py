"""``bellman attribute rename`` and the underlying rewrite."""

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
    write_project,
)
from typer.testing import CliRunner

from bellman import layout
from bellman.attributes.rename import rename_attribute_value
from bellman.cli import app
from bellman.errors import BellmanLayoutError
from bellman.roadmap import load
from bellman.validate import validate_roadmap

runner = CliRunner()


def _setup(tmp_path: Path) -> Path:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_attribute(root, "program", PROGRAM_JSONC)
    return root


def _errors(root: Path) -> list[str]:
    return [e.message for e in validate_roadmap(load(root)).errors]


def test_renames_set_member_in_definition_and_markdown(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    alpha = write_initiative(root, "alpha", ["priority: P1"])
    beta = write_project(root, "beta", ["priority: P1"])
    other = write_initiative(root, "other", ["priority: P2"])
    before_other = other.read_text(encoding="utf-8")

    result = rename_attribute_value(root, "priority", "P1", "high")

    assert result.assignments == 2
    assert set(result.updated_paths) == {alpha, beta}
    assert "- priority: high\n" in alpha.read_text(encoding="utf-8")
    assert "- priority: high\n" in beta.read_text(encoding="utf-8")
    assert other.read_text(encoding="utf-8") == before_other
    definition = (root / "attributes" / "priority.jsonc").read_text(encoding="utf-8")
    assert '"values": ["P0", "high", "P2"]' in definition
    assert _errors(root) == []


def test_keeps_pin_and_payload_and_comments(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    path = write_initiative(
        root, "alpha", ["priority: P1", "program@1.2: platform-v2 [allocation: 0.5]"]
    )
    rename_attribute_value(root, "program", "platform-v2", "platform-v3")
    text = path.read_text(encoding="utf-8")
    assert "- program@1.2: platform-v3 [allocation: 0.5]\n" in text
    definition = (root / "attributes" / "program.jsonc").read_text(encoding="utf-8")
    assert "// Speculative work scope with data per program." in definition
    assert '"version": "1.2"' in definition
    assert '"platform-v3": { "title": "Platform v2", "probability": 0.4 }' in definition
    assert '"platform-v2"' not in definition
    assert _errors(root) == []


def test_only_rewrites_inside_classifications_section(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    text = path.read_text(encoding="utf-8").replace(
        "## Introduction\n\nIntro.", "## Introduction\n\n- priority: P1\n"
    )
    path.write_text(text, encoding="utf-8")
    rename_attribute_value(root, "priority", "P1", "high")
    out = path.read_text(encoding="utf-8")
    assert out.count("- priority: P1\n") == 1
    assert out.count("- priority: high\n") == 1
    assert out.index("- priority: P1") < out.index("## Classifications")


def test_identical_strings_elsewhere_in_definition_are_untouched(
    tmp_path: Path,
) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "tag",
        """{
  "name": "tag",
  "version": "1.0",
  "applies_to": ["goal"],
  "cardinality": "many",
  "description": "alpha is the first",
  "values": ["beta", "alpha"],
  "assignment_schema": {
    "type": "object",
    "properties": { "alpha": { "enum": ["alpha"] } }
  }
}
""",
    )
    write_goal(root, "g", ["tag: alpha"])
    rename_attribute_value(root, "tag", "alpha", "gamma")
    text = (root / "attributes" / "tag.jsonc").read_text(encoding="utf-8")
    assert '"values": ["beta", "gamma"]' in text
    assert '"description": "alpha is the first"' in text
    assert '"properties": { "alpha": { "enum": ["alpha"] } }' in text
    assert _errors(root) == []


def test_work_package_yaml_forms(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    classifications = (
        "      program: platform-v2  # inline\n      priority-x: platform-v2\n"
    )
    yaml_text = wp_yaml(
        wp_block("inline", classifications),
        wp_block(
            "as-list",
            "      program:\n        - platform-v2\n        - data-residency\n",
        ),
        wp_block(
            "as-value",
            "      # note\n"
            "      program@1.2:\n"
            "        - value: platform-v2\n"
            "          allocation: 0.5\n"
            "        - value: data-residency\n",
        ),
        wp_block("quoted", '      program: "platform-v2"\n'),
        wp_block("same-indent", "      program:\n      - platform-v2\n"),
        (
            "  - title: nested\n"
            "    description: Do it.\n"
            "    classifications:\n"
            "      program: data-residency\n"
            "    sub_packages:\n"
            "      - title: child\n"
            "        description: Do it.\n"
            "        estimate: [1d, 2d, 3d]\n"
            "        classifications:\n"
            "          program: platform-v2\n"
        ),
    )
    # ``priority-x`` is not an attribute: drop it to keep the file valid.
    yaml_text = yaml_text.replace("      priority-x: platform-v2\n", "")
    write_project(root, "beta", ["priority: P1"], work_packages=yaml_text)
    path = root / "projects" / "beta" / "work-packages.yaml"

    result = rename_attribute_value(root, "program", "platform-v2", "platform-v3")

    assert result.assignments == 6 - 0
    assert path in result.updated_paths
    out = path.read_text(encoding="utf-8")
    assert "platform-v2" not in out
    assert "program: platform-v3  # inline\n" in out
    assert "        - platform-v3\n        - data-residency\n" in out
    assert "        - value: platform-v3\n          allocation: 0.5\n" in out
    assert '      program: "platform-v3"\n' in out
    assert "      - platform-v3\n" in out
    assert "          program: platform-v3\n" in out
    assert "      # note\n" in out
    assert _errors(root) == []


def test_work_package_rewrite_leaves_other_attributes(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_attribute(
        root,
        "stage",
        json.dumps(
            {
                "name": "stage",
                "version": "1.0",
                "applies_to": ["work_package"],
                "cardinality": "one",
                "values": ["platform-v2", "ga"],
            }
        ),
    )
    write_project(
        root,
        "beta",
        ["priority: P1"],
        work_packages=wp_yaml(
            wp_block("a", "      program: platform-v2\n      stage: platform-v2\n"),
        ),
    )
    path = root / "projects" / "beta" / "work-packages.yaml"
    rename_attribute_value(root, "program", "platform-v2", "platform-v3")
    out = path.read_text(encoding="utf-8")
    assert "program: platform-v3\n" in out
    assert "stage: platform-v2\n" in out


def test_parked_project_and_other_kinds_are_rewritten(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_attribute(
        root,
        "stage",
        json.dumps(
            {
                "name": "stage",
                "version": "1.0",
                "applies_to": ["goal"],
                "cardinality": "one",
                "values": ["draft", "live"],
            }
        ),
    )
    goal = write_goal(root, "g", ["stage: draft"])
    project = write_project(root, "beta", ["priority: P1"])
    archived_dir = project.parent.with_name("beta.archived")
    project.parent.rename(archived_dir)
    parked = archived_dir / "beta.md"
    parked_text = parked.read_text(encoding="utf-8")
    parked.write_text(parked_text.replace("priority: P1", "priority: P2"))

    result = rename_attribute_value(root, "stage", "draft", "live-soon")
    assert result.updated_paths == (goal,)

    again = rename_attribute_value(root, "priority", "P2", "low")
    assert again.updated_paths == (parked,)
    assert "- priority: low\n" in parked.read_text(encoding="utf-8")


def test_crlf_line_endings_are_preserved(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    rename_attribute_value(root, "priority", "P1", "high")
    data = path.read_bytes()
    assert b"- priority: high\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (("nope", "P1", "x"), "unknown attribute 'nope'"),
        (("priority", "P7", "x"), "'P7' is not a value of attribute 'priority'"),
        (("priority", "P1", "P2"), "'P2' is already a value"),
        (("priority", "P1", "P1"), "already named"),
        (("priority", "P1", "bad value"), "new value 'bad value'"),
        (("priority", "-x", "ok"), "old value '-x'"),
        (("Priority", "P1", "x"), "kebab"),
    ],
)
def test_refusals(tmp_path: Path, args: tuple[str, str, str], fragment: str) -> None:
    root = _setup(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    before = path.read_text(encoding="utf-8")
    with pytest.raises((BellmanLayoutError, ValueError)) as excinfo:
        rename_attribute_value(root, *args)
    message = getattr(excinfo.value, "message", str(excinfo.value))
    assert fragment in message
    assert path.read_text(encoding="utf-8") == before


def test_open_attribute_cannot_be_renamed(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(
        root,
        "budget",
        "{"
        + PRIORITY_JSONC.split("{", 1)[1]
        .replace('"values": ["P0", "P1", "P2"]', '"value_schema": {"type": "number"}')
        .replace("priority", "budget"),
    )
    with pytest.raises(BellmanLayoutError, match="no fixed values"):
        rename_attribute_value(root, "budget", "1", "2")


def test_invalid_definition_syntax_is_refused(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", "{ nope")
    with pytest.raises(BellmanLayoutError, match="invalid attribute definition"):
        rename_attribute_value(root, "priority", "P1", "x")


def test_nothing_is_written_when_a_file_cannot_be_rewritten(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    alpha = write_initiative(root, "alpha", ["priority: P1"])
    yaml_text = wp_yaml(
        wp_block("flow", "      program: [platform-v2, data-residency]\n"),
    )
    write_project(root, "beta", ["priority: P1"], work_packages=yaml_text)
    before = {
        p: p.read_text(encoding="utf-8")
        for p in (
            alpha,
            root / "attributes" / "program.jsonc",
            root / "projects" / "beta" / "work-packages.yaml",
        )
    }
    with pytest.raises(BellmanLayoutError, match="could not rewrite program"):
        rename_attribute_value(root, "program", "platform-v2", "platform-v3")
    assert {p: p.read_text(encoding="utf-8") for p in before} == before


def test_invalid_classification_syntax_is_refused(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    path.write_text(
        path.read_text(encoding="utf-8") + "- this is not valid\n", encoding="utf-8"
    )
    with pytest.raises(BellmanLayoutError, match="alpha.md"):
        rename_attribute_value(root, "priority", "P1", "high")
    assert "high" not in (root / "attributes" / "priority.jsonc").read_text(
        encoding="utf-8"
    )


def test_invalid_work_packages_yaml_is_refused(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_project(root, "beta", ["priority: P1"], work_packages="a: [unclosed\n")
    with pytest.raises(BellmanLayoutError, match="invalid YAML"):
        rename_attribute_value(root, "priority", "P1", "high")


def test_invalid_work_package_classifications_are_refused(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_project(
        root,
        "beta",
        ["priority: P1"],
        work_packages=wp_yaml(wp_block("a", "      - not-a-mapping\n")),
    )
    with pytest.raises(BellmanLayoutError):
        rename_attribute_value(root, "priority", "P1", "high")


def test_work_packages_yaml_that_is_not_a_mapping_is_skipped(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_project(root, "beta", ["priority: P1"], work_packages="- just\n- a list\n")
    result = rename_attribute_value(root, "priority", "P1", "high")
    assert result.assignments == 1


def test_cli_attribute_rename(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    result = runner.invoke(
        app, ["attribute", "rename", "priority", "P1", "high", "--path", str(root)]
    )
    assert result.exit_code == 0, result.output
    assert (
        "Renamed priority: P1 -> high (1 assignment(s) in 1 file(s))" in result.output
    )
    assert "Bump the major version in attributes/priority.jsonc" in result.output
    assert "- priority: high\n" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (["priority", "P7", "x"], "not a value"),
        (["priority", "P1", "bad value"], "new value"),
    ],
)
def test_cli_attribute_rename_errors(
    tmp_path: Path, args: list[str], fragment: str
) -> None:
    root = _setup(tmp_path)
    result = runner.invoke(app, ["attribute", "rename", *args, "--path", str(root)])
    assert result.exit_code == 1
    assert fragment in result.output


def test_entity_rename_does_not_touch_classification_keys(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    # An initiative named like an attribute and like a value.
    write_initiative(root, "priority", ["priority: P1"])
    other = write_initiative(root, "other", ["priority: P1", "program: platform-v2"])
    before = other.read_text(encoding="utf-8")

    layout.rename_entity(root, "priority", "urgency", kind="initiative")

    assert other.read_text(encoding="utf-8") == before
    renamed = root / layout.INITIATIVES_DIR / "urgency.md"
    assert "- priority: P1\n" in renamed.read_text(encoding="utf-8")
    assert _errors(root) == []
