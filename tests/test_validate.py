"""Validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from snark.roadmap import load
from snark.validate import validate_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_example_roadmap_validates() -> None:
    roadmap = load(EXAMPLES)
    errors = validate_roadmap(roadmap)
    assert errors == []


def _write_goal(root: Path, name: str, content: str) -> None:
    goal_dir = root / "goals"
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / f"{name}.md").write_text(content, encoding="utf-8")


def test_goal_header_must_match_name(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# Wrong Title\n\nSome content.\n")
    roadmap = load(tmp_path)
    errors = validate_roadmap(roadmap)
    assert any("does not match name" in e.message for e in errors)


def test_goal_header_match_is_case_insensitive(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# REDUCE CHURN\n\nSome content.\n")
    roadmap = load(tmp_path)
    errors = validate_roadmap(roadmap)
    assert errors == []


def test_goal_requires_content_beneath_header(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "# Reduce Churn\n\n")
    roadmap = load(tmp_path)
    errors = validate_roadmap(roadmap)
    assert any("missing content beneath header" in e.message for e in errors)


def test_goal_missing_header_fails_at_load(tmp_path: Path) -> None:
    _write_goal(tmp_path, "reduce-churn", "No heading here.\n")
    with pytest.raises(ValueError, match="missing top-level header"):
        load(tmp_path)
