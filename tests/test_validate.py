"""Validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bellman.roadmap import load
from bellman.validate import validate_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_example_roadmap_validates() -> None:
    roadmap = load(EXAMPLES)
    result = validate_roadmap(roadmap)
    assert result.errors == ()
    assert result.warnings == ()


def _write_goal(root: Path, name: str, content: str) -> None:
    goal_dir = root / "goals"
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / f"{name}.md").write_text(content, encoding="utf-8")


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


def test_goal_header_must_match_name(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# Wrong Title\n\nSome content.\n")
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("does not match name" in e.message for e in result.errors)


def test_goal_header_match_is_case_insensitive(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# REDUCE CHURN\n\nSome content.\n")
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert result.errors == ()


def test_goal_requires_content_beneath_header(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# Reduce Churn\n\n")
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("missing content beneath header" in e.message for e in result.errors)


def test_goal_missing_header_fails_at_load(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "No heading here.\n")
    with pytest.raises(ValueError, match="missing top-level header"):
        load(tmp_path)


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
