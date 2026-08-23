"""Parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bellman.model import UNKNOWN_ESTIMATE, ThreePointEstimate
from bellman.parse.dependencies import parse_dependencies_section
from bellman.parse.work_packages import _parse_estimate_value, parse_work_packages
from bellman.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_parse_dependencies() -> None:
    body = "- foo [FS, Mandatory]\n"
    edges = parse_dependencies_section(body, successor="bar")
    assert len(edges) == 1
    assert edges[0].predecessor == "foo"
    assert edges[0].successor == "bar"


def test_parse_dependencies_rejects_after() -> None:
    with pytest.raises(ValueError, match="after:/before:"):
        parse_dependencies_section("- after: foo [FS, Mandatory]\n", successor="bar")


def test_parse_dependencies_rejects_before() -> None:
    with pytest.raises(ValueError, match="after:/before:"):
        parse_dependencies_section("- before: foo [FS, Mandatory]\n", successor="bar")


def test_load_example_roadmap() -> None:
    roadmap = load(EXAMPLES)
    assert len(roadmap.initiatives) == 1
    assert len(roadmap.projects) == 1
    assert roadmap.project_by_name("billing-redesign") is not None
    wps = roadmap.project_by_name("billing-redesign").work_packages  # type: ignore[union-attr]
    assert len(wps) == 1
    assert wps[0].slug == "wp-invoicing"
    assert wps[0].title == "wp-invoicing"
    assert len(wps[0].sub_packages) == 1


def test_parse_work_packages_file() -> None:
    wp_path = EXAMPLES / "projects" / "billing-redesign" / "work-packages.yaml"
    packages = parse_work_packages(wp_path, project_name="billing-redesign")
    assert packages[0].estimate is None
    assert packages[0].sub_packages[0].slug == "wp-pdf-export"
    assert packages[0].sub_packages[0].title == "wp-pdf-export"
    assert isinstance(packages[0].sub_packages[0].estimate, ThreePointEstimate)


def test_parse_unknown_estimate() -> None:
    assert _parse_estimate_value("unknown", "path", "wp") is UNKNOWN_ESTIMATE
    assert _parse_estimate_value("Unknown", "path", "wp") is UNKNOWN_ESTIMATE


def test_parse_full_estimate() -> None:
    raw = ["1w", "2w", "3w"]
    est = _parse_estimate_value(raw, "path", "wp")
    assert isinstance(est, ThreePointEstimate)
    assert est.optimistic == 1.0
    assert est.most_likely == 2.0
    assert est.pessimistic == 3.0
    assert est.unit == "w"


def test_parse_mixed_duration_suffixes_fails() -> None:
    raw = ["1w", "2d", "3w"]
    with pytest.raises(ValueError, match="same duration suffix"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_requires_suffix() -> None:
    raw = [1, "2w", "3w"]
    with pytest.raises(ValueError, match="must be a duration with h, d, or w suffix"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_allows_equal_values() -> None:
    raw = ["2w", "2w", "2w"]
    est = _parse_estimate_value(raw, "path", "wp")
    assert isinstance(est, ThreePointEstimate)
    assert est.optimistic == est.most_likely == est.pessimistic == 2.0


def test_parse_estimate_rejects_out_of_order_values() -> None:
    raw = ["7w", "2w", "1w"]
    with pytest.raises(
        ValueError,
        match="optimistic <= most_likely <= pessimistic",
    ):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_partial_estimate_fails() -> None:
    raw = ["1w", "2w"]
    with pytest.raises(ValueError, match="incomplete estimate"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_partial_unknown_in_estimate_fails() -> None:
    raw = ["unknown", "2w", "3w"]
    with pytest.raises(ValueError, match="partial estimate with unknown"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_rejects_mapping() -> None:
    raw = {
        "optimistic": "1w",
        "most_likely": "2w",
        "pessimistic": "3w",
    }
    with pytest.raises(ValueError, match="must be unknown or"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_invalid_estimate_body_fails() -> None:
    with pytest.raises(ValueError, match="must be unknown or \\[optimistic"):
        _parse_estimate_value("TBD", "path", "wp")


def test_parse_rejects_estimate_with_sub_packages(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-parent\n"
        "    description: Parent work.\n"
        "    estimate: unknown\n"
        "    sub_packages:\n"
        "      - title: wp-child\n"
        "        description: Child work.\n"
        "        estimate: unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not have its own estimate"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_title_derives_slug() -> None:
    wp_path = EXAMPLES.parent / "tmp-wp.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: PDF Export\n"
        "    description: Generate PDFs.\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    try:
        packages = parse_work_packages(wp_path, project_name="demo")
        assert packages[0].slug == "pdf-export"
        assert packages[0].title == "PDF Export"
    finally:
        wp_path.unlink()


def test_parse_notes() -> None:
    wp_path = EXAMPLES.parent / "tmp-wp.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Short.\n"
        "    notes: |\n"
        "      Line one.\n"
        "      Line two.\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    try:
        packages = parse_work_packages(wp_path, project_name="demo")
        assert "Line one." in packages[0].notes
        assert "Line two." in packages[0].notes
    finally:
        wp_path.unlink()


def test_parse_invalid_duration_string(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a duration"):
        _parse_estimate_value(["1x", "2w", "3w"], "path", "wp")


def test_parse_dependency_string_form(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-a\n"
        "    description: A.\n"
        "    estimate: unknown\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - wp-a [FS, Mandatory]\n",
        encoding="utf-8",
    )
    packages = parse_work_packages(wp_path, project_name="demo")
    assert packages[1].dependencies[0].predecessor == "wp-a"
    assert packages[1].dependencies[0].successor == "demo/wp-b"


def test_parse_dependency_dict_form(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-a\n"
        "    description: A.\n"
        "    estimate: unknown\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - predecessor: wp-a\n"
        "        relation: SS\n"
        "        hardness: Optional\n",
        encoding="utf-8",
    )
    packages = parse_work_packages(wp_path, project_name="demo")
    edge = packages[1].dependencies[0]
    assert edge.predecessor == "wp-a"
    assert edge.relation.value == "SS"
    assert edge.hardness.value == "Optional"


def test_parse_dependency_legacy_dict_fails(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - after: wp-a\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="after:/before:"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_invalid_type(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - 42\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid dependency"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_legacy_string_fails(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        '      - "after: wp-a [FS, Mandatory]"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="after:/before:"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_invalid_string(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - not-a-valid-dep\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid dependency syntax"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_not_list(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies: wp-a\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dependencies must be a list"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_missing_predecessor(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - relation: FS\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing predecessor"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependency_invalid_relation(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - predecessor: wp-a\n"
        "        relation: XX\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid dependency"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_missing_title(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - description: No title.\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing title"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_missing_description(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\nwork_packages:\n  - title: wp-foo\n    estimate: unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing description"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_notes_must_be_string(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: D.\n"
        "    notes: [1, 2]\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="notes must be a string"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_notes_null_ok(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: D.\n"
        "    notes: null\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    packages = parse_work_packages(wp_path, project_name="demo")
    assert packages[0].notes == ""


def test_parse_wp_sub_packages_null(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: D.\n"
        "    estimate: unknown\n"
        "    sub_packages: null\n",
        encoding="utf-8",
    )
    packages = parse_work_packages(wp_path, project_name="demo")
    assert packages[0].sub_packages == ()


def test_parse_wp_sub_packages_not_list(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: D.\n"
        "    sub_packages: nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sub_packages must be a list"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_entry_not_mapping(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(
        "version: 1\n\nwork_packages:\n  - just-a-string\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be a mapping"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_invalid_yaml(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(":\n  - bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_empty_file(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text("", encoding="utf-8")
    assert parse_work_packages(wp_path, project_name="demo") == []


def test_parse_wp_not_mapping_root(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_unsupported_version(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text("version: 99\nwork_packages: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported work-packages version"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_wp_packages_null(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text("version: 1\nwork_packages: null\n", encoding="utf-8")
    assert parse_work_packages(wp_path, project_name="demo") == []


def test_parse_wp_packages_not_list(tmp_path: Path) -> None:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text("version: 1\nwork_packages: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="work_packages must be a list"):
        parse_work_packages(wp_path, project_name="demo")


def test_parse_dependencies_invalid_line() -> None:
    with pytest.raises(ValueError, match="expected"):
        parse_dependencies_section("- not valid\n", successor="bar")


def test_parse_dependencies_skips_comments() -> None:
    edges = parse_dependencies_section(
        "# comment\n\n- foo [FS, Mandatory]\n",
        successor="bar",
    )
    assert len(edges) == 1


def test_parse_milestone_ok(tmp_path: Path) -> None:
    from bellman.parse.milestone import parse_milestone

    path = tmp_path / "ship-it.md"
    path.write_text(
        "# Ship It\n\n## Date\n\n2026-01-15\n\n## Description\n\nReady.\n",
        encoding="utf-8",
    )
    ms = parse_milestone(path)
    assert ms.name == "ship-it"
    assert ms.date == "2026-01-15"
    assert "Ready" in ms.description


def test_parse_milestone_missing_title(tmp_path: Path) -> None:
    from bellman.parse.milestone import parse_milestone

    path = tmp_path / "no-title.md"
    path.write_text("## Date\n\n2026-01-15\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing title"):
        parse_milestone(path)


def test_parse_milestone_missing_date(tmp_path: Path) -> None:
    from bellman.parse.milestone import parse_milestone

    path = tmp_path / "no-date.md"
    path.write_text("# No Date\n\n## Description\n\nOops.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing ## Date"):
        parse_milestone(path)


def test_parse_work_scope_missing_section(tmp_path: Path) -> None:
    from bellman.parse.work_scope import parse_work_scope

    path = tmp_path / "init.md"
    path.write_text("# Init\n\n## Introduction\n\nHi.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required section"):
        parse_work_scope(path, is_project=False)


def test_parse_work_scope_missing_title(tmp_path: Path) -> None:
    from bellman.parse.work_scope import parse_work_scope

    path = tmp_path / "init.md"
    path.write_text("## Introduction\n\nHi.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing title"):
        parse_work_scope(path, is_project=False)


def test_parse_work_scope_project_criteria_h2(tmp_path: Path) -> None:
    from bellman.parse.work_scope import parse_work_scope

    path = tmp_path / "proj.md"
    path.write_text(
        "# Proj\n\n"
        "## Introduction\n\nIntro.\n\n"
        "## Motivation\n\nWhy.\n\n"
        "## Detailed Description\n\nDetails.\n\n"
        "## Criteria for Success\n\nDone.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    project = parse_work_scope(path, is_project=True, name="proj")
    assert "Done" in project.criteria_for_success


def test_parse_work_scope_criteria_embedded_in_detailed(tmp_path: Path) -> None:
    from bellman.parse.work_scope import parse_work_scope

    path = tmp_path / "proj.md"
    path.write_text(
        "# Proj\n\n"
        "## Introduction\n\nIntro.\n\n"
        "## Motivation\n\nWhy.\n\n"
        "## Detailed Description\n\n"
        "Details before.\n\n"
        "### Criteria for Success\n\n"
        "Embedded done.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    project = parse_work_scope(path, is_project=True, name="proj")
    assert "Embedded done" in project.criteria_for_success
    assert "Details before" in project.detailed_description
    assert "Criteria for Success" not in project.detailed_description


def test_subsections_utility() -> None:
    from bellman.parse._sections import Section, subsections

    parent = Section(level=2, title="Parent", body="", line=1)
    child = Section(level=3, title="Child", body="c", line=2)
    sibling = Section(level=2, title="Sibling", body="", line=3)
    assert subsections(parent, [parent, child, sibling]) == [child]
    assert subsections(parent, [child]) == []


def test_goal_with_h2_section(tmp_path: Path) -> None:
    from bellman.parse.goal import parse_goal

    path = tmp_path / "reduce-churn.md"
    path.write_text(
        "# Reduce Churn\n\n## Notes\n\nExtra section body.\n",
        encoding="utf-8",
    )
    goal = parse_goal(path)
    assert "Extra section body" in goal.description
