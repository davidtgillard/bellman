"""Validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bellman import layout
from bellman.roadmap import load, load_for_validation
from bellman.validate import validate_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_example_roadmap_validates() -> None:
    roadmap = load(EXAMPLES)
    result = validate_roadmap(roadmap)
    assert result.errors == ()
    assert result.warnings == ()


def _write_project_with_wp(root: Path, wp_content: str) -> None:
    project_dir = root / "projects" / "billing-redesign"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "billing-redesign.md").write_text(
        "# Billing Redesign\n\n"
        "## Introduction\n\nTBD.\n\n"
        "## Motivation\n\nTBD.\n\n"
        "## Detailed Description\n\nTBD.\n\n"
        "### Criteria for Success\n\nShip it.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    (project_dir / "work-packages.yaml").write_text(wp_content, encoding="utf-8")


def test_unknown_estimate_warns(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n"
        "    estimate: unknown\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert result.errors == ()
    assert len(result.warnings) == 1
    assert "unknown estimate" in result.warnings[0].message


def test_parent_with_estimate_and_sub_packages_errors(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-parent\n"
        "    description: Parent work.\n"
        "    estimate: [1w, 2w, 3w]\n"
        "    sub_packages:\n"
        "      - title: wp-child\n"
        "        description: Child work.\n"
        "        estimate: unknown\n",
    )
    with pytest.raises(ValueError, match="must not have its own estimate"):
        load(tmp_path)


def test_parent_with_sub_packages_requires_no_estimate(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-parent\n"
        "    description: Parent work.\n"
        "    sub_packages:\n"
        "      - title: wp-child\n"
        "        description: Child work.\n"
        "        estimate: unknown\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert result.errors == ()
    assert len(result.warnings) == 1
    assert "unknown estimate" in result.warnings[0].message


def test_missing_estimate_errors(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert len(result.errors) == 1
    assert "missing estimate" in result.errors[0].message
    assert result.warnings == ()


def test_validate_rejects_legacy_after_in_markdown(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "follower")
    path = layout.initiative_path(tmp_path, "follower")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- after: other [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    result = load_for_validation(tmp_path)
    assert any("after:/before:" in e.message for e in result.errors)


def test_validate_rejects_legacy_after_in_work_packages(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - after: wp-bar\n",
    )
    result = load_for_validation(tmp_path)
    assert any("after:/before:" in e.message for e in result.errors)


def test_initiative_project_name_overlap(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "shared-name")
    layout.create_project(tmp_path, "shared-name")
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("both named" in e.message for e in result.errors)


def test_project_missing_criteria(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    project_dir = tmp_path / "projects" / "nocrit"
    project_dir.mkdir(parents=True)
    (project_dir / "nocrit.md").write_text(
        "# Nocrit\n\n"
        "## Introduction\n\nTBD.\n\n"
        "## Motivation\n\nTBD.\n\n"
        "## Detailed Description\n\nTBD.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("Criteria for Success" in e.message for e in result.errors)


def test_duplicate_work_package_slug(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-dup\n"
        "    description: One.\n"
        "    estimate: unknown\n"
        "  - title: wp-dup\n"
        "    description: Two.\n"
        "    estimate: unknown\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("duplicate work package slug" in e.message for e in result.errors)


def test_unknown_dependency_predecessor(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - predecessor: missing-wp\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("unknown dependency" in e.message for e in result.errors)


def test_qualified_wp_dependency_ok(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-a\n"
        "    description: A.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "    dependencies:\n"
        "      - predecessor: billing-redesign/wp-a\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert not any("unknown dependency" in e.message for e in result.errors)


def test_mandatory_wp_cycle(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-a\n"
        "    description: A.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "    dependencies:\n"
        "      - predecessor: wp-b\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "    dependencies:\n"
        "      - predecessor: wp-a\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("mandatory precedence cycle" in e.message for e in result.errors)


def test_discretionary_cycle_allowed(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-a\n"
        "    description: A.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "    dependencies:\n"
        "      - predecessor: wp-b\n"
        "        hardness: Discretionary\n"
        "  - title: wp-b\n"
        "    description: B.\n"
        "    estimate: [1d, 1d, 1d]\n"
        "    dependencies:\n"
        "      - predecessor: wp-a\n"
        "        hardness: Discretionary\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert not any("cycle" in e.message for e in result.errors)


def test_scope_dependency_unknown(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "follower")
    path = layout.initiative_path(tmp_path, "follower")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- missing-pred [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("unknown dependency" in e.message for e in result.errors)


def test_scope_mandatory_cycle(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "alpha")
    layout.create_initiative(tmp_path, "beta")
    alpha = layout.initiative_path(tmp_path, "alpha")
    beta = layout.initiative_path(tmp_path, "beta")
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- beta [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    beta.write_text(
        beta.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- alpha [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("cycle among work scopes" in e.message for e in result.errors)


def test_milestone_placeholder_date(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_milestone(tmp_path, "ship")
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("YYYY-MM-DD" in e.message for e in result.errors)


def test_qualified_unknown_wp_dependency(tmp_path: Path) -> None:
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n"
        "    estimate: unknown\n"
        "    dependencies:\n"
        "      - predecessor: billing-redesign/missing-wp\n",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("unknown dependency" in e.message for e in result.errors)


def test_ambiguous_dependency_ref(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "shared")
    layout.create_milestone(tmp_path, "shared")
    layout.create_initiative(tmp_path, "follower")
    path = layout.initiative_path(tmp_path, "follower")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- shared [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("ambiguous" in e.message for e in result.errors)
