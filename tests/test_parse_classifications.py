"""Parsing of attribute assignments from markdown and work-package YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
from attr_support import (
    make_root,
    wp_block,
    wp_yaml,
    write_initiative,
    write_milestone,
    write_project,
)

from bellman.model import AttributeAssignment
from bellman.parse.classifications import (
    parse_classifications_section,
    parse_classifications_yaml,
    parse_version,
    split_classifications_section,
    split_name_and_pin,
)
from bellman.roadmap import load


def test_parse_version() -> None:
    assert parse_version("1.2") == (1, 2)
    assert parse_version("0.10") == (0, 10)


@pytest.mark.parametrize("text", ["1", "1.2.3", "01.2", "1.02", "a.b", "", "1."])
def test_parse_version_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="invalid version"):
        parse_version(text)


def test_split_name_and_pin() -> None:
    assert split_name_and_pin("program") == ("program", None)
    assert split_name_and_pin("program@1.2") == ("program", (1, 2))


@pytest.mark.parametrize("head", ["", "@1.0", "Program", "pro_gram", "a b"])
def test_split_name_and_pin_rejects_bad_names(head: str) -> None:
    with pytest.raises(ValueError, match=r"invalid attribute|kebab"):
        split_name_and_pin(head)


def test_split_name_and_pin_rejects_bad_pin() -> None:
    with pytest.raises(ValueError, match="invalid version"):
        split_name_and_pin("program@1")


def test_section_simple_and_pinned_with_payload() -> None:
    body = (
        "- priority: P1\n"
        '- program@1.0: platform-v2 [allocation: 0.5, note: "a, b", ok: true, n: 3]\n'
    )
    assert parse_classifications_section(body) == (
        AttributeAssignment("priority", "P1"),
        AttributeAssignment(
            "program",
            "platform-v2",
            {"allocation": 0.5, "note": "a, b", "ok": True, "n": 3},
            (1, 0),
        ),
    )


def test_section_payload_types_and_bare_strings() -> None:
    (assignment,) = parse_classifications_section(
        '- x: v [a: no, b: false, c: -2, d: 1.5e3, e: "q"]'
    )
    assert dict(assignment.payload) == {
        "a": "no",
        "b": False,
        "c": -2,
        "d": 1500.0,
        "e": "q",
    }


def test_section_skips_blank_and_comment_lines() -> None:
    body = "\n# a comment\n- priority: P1\n\n"
    assert len(parse_classifications_section(body)) == 1


def test_section_empty_payload_brackets() -> None:
    (assignment,) = parse_classifications_section("- priority: P1 []")
    assert dict(assignment.payload) == {}


@pytest.mark.parametrize(
    "line",
    [
        "priority: P1",
        "- priority P1",
        "- priority: two words",
        "- priority: P1 trailing",
        "- priority: [x: 1]",
        "- Priority: P1",
        "- priority:",
    ],
)
def test_section_rejects_bad_lines(line: str) -> None:
    with pytest.raises(ValueError, match="invalid classification"):
        parse_classifications_section(line)


def test_section_rejects_bad_name_with_line_number() -> None:
    with pytest.raises(ValueError, match=r"at line 2.*kebab"):
        parse_classifications_section("- ok: A\n- Bad_Name: B")


def test_section_rejects_bad_pin() -> None:
    with pytest.raises(ValueError, match="invalid version"):
        parse_classifications_section("- program@1: x")


@pytest.mark.parametrize("payload", ["noval", "a:", "1a: 2", "a: 1, a: 2"])
def test_section_rejects_bad_payload(payload: str) -> None:
    with pytest.raises(ValueError, match="payload"):
        parse_classifications_section(f"- x: v [{payload}]")


def test_split_classifications_section() -> None:
    text = "# T\n\nbody\n\n## Classifications\n\n- a: b\n\n## Other\n\nmore\n"
    rest, body = split_classifications_section(text)
    assert body == "- a: b"
    assert "Classifications" not in rest
    assert "## Other" in rest
    assert "- a: b" not in rest


def test_split_classifications_section_absent() -> None:
    text = "# T\n\n## Intro\n\nx\n"
    assert split_classifications_section(text) == (text, None)


def test_split_classifications_section_keeps_deeper_headings_inside() -> None:
    text = "# T\n\n## Classifications\n\n### Sub\n\n- a: b\n"
    rest, body = split_classifications_section(text)
    assert body is not None
    assert "### Sub" in body
    assert "Classifications" not in rest


def test_yaml_scalars_lists_and_payloads() -> None:
    raw = {
        "priority": "P1",
        "program@1.0": [
            {"value": "platform-v2", "allocation": 0.5},
            "data-residency",
        ],
        "budget": {"value": 12, "currency": "usd"},
        "open": {"value": {"low": 1, "high": 2}},
        "flag": True,
    }
    result = parse_classifications_yaml(raw, path="wp.yaml", owner="wp-a")
    assert result == (
        AttributeAssignment("priority", "P1"),
        AttributeAssignment("program", "platform-v2", {"allocation": 0.5}, (1, 0)),
        AttributeAssignment("program", "data-residency", {}, (1, 0)),
        AttributeAssignment("budget", 12, {"currency": "usd"}),
        AttributeAssignment("open", {"low": 1, "high": 2}),
        AttributeAssignment("flag", True),
    )


def test_yaml_none_is_empty() -> None:
    assert parse_classifications_yaml(None, path="p", owner="o") == ()


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        (["a"], "must be a mapping"),
        ({"Bad": "x"}, "invalid classification"),
        ({"a": None}, "invalid value"),
        ({"a": {"allocation": 1}}, "missing 'value'"),
        ({"a": {"value": "x", "nested": {"k": 1}}}, "flat scalars"),
        ({"a": {"value": {"k": [1]}}}, "flat scalars"),
        ({"a": {"value": None}}, "invalid value"),
        ({"a": [["x"]]}, "invalid value"),
    ],
)
def test_yaml_rejects(raw: object, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        parse_classifications_yaml(raw, path="wp.yaml", owner="wp-a")


def test_entities_load_classifications(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_initiative(root, "alpha", ["priority: P2"])
    write_initiative(root, "plain")
    write_project(
        root,
        "beta",
        ["priority: P1", "program@1.0: platform-v2 [allocation: 0.5]"],
        work_packages=wp_yaml(
            wp_block(
                "wp-one",
                "      priority: P0\n"
                "      program:\n"
                "        - value: platform-v2\n"
                "          allocation: 0.25\n",
            ),
            wp_block("wp-two"),
        ),
    )
    write_milestone(root, "ga", ["priority: P0"])
    roadmap = load(root)

    alpha = roadmap.initiative_by_name("alpha")
    assert alpha is not None
    assert alpha.classifications == (AttributeAssignment("priority", "P2"),)
    plain = roadmap.initiative_by_name("plain")
    assert plain is not None
    assert plain.classifications == ()

    beta = roadmap.project_by_name("beta")
    assert beta is not None
    assert [a.name for a in beta.classifications] == ["priority", "program"]
    assert beta.classifications[1].pinned_version == (1, 0)
    assert beta.classifications[1].payload == {"allocation": 0.5}
    assert beta.criteria_for_success == "Ship it."
    wp_one, wp_two = beta.work_packages
    assert [a.name for a in wp_one.classifications] == ["priority", "program"]
    assert wp_one.classifications[1].payload == {"allocation": 0.25}
    assert wp_two.classifications == ()

    milestone = roadmap.milestone_by_name("ga")
    assert milestone is not None
    assert milestone.classifications == (AttributeAssignment("priority", "P0"),)
    assert milestone.description == "Ship."


def test_bad_classification_line_is_a_load_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_initiative(root, "alpha", ["not valid"])
    with pytest.raises(ValueError, match="invalid classification syntax"):
        load(root)


def test_bad_work_package_classifications_is_a_load_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_project(
        root,
        "beta",
        work_packages=wp_yaml(wp_block("wp-one", "      - nope\n")),
    )
    with pytest.raises(ValueError, match="classifications must be a mapping"):
        load(root)
