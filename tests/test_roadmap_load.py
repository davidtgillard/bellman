"""Tests for forgiving roadmap loading."""

from __future__ import annotations

from pathlib import Path

from bellman.roadmap import load_for_validation


def test_load_for_validation_collects_multiple_errors(tmp_path: Path) -> None:
    goals = tmp_path / "goals"
    goals.mkdir(parents=True)
    (goals / "bad-a.md").write_text("no header\n", encoding="utf-8")
    (goals / "bad-b.md").write_text("also no header\n", encoding="utf-8")

    result = load_for_validation(tmp_path)

    assert len(result.errors) == 2
    assert result.roadmap.goals == ()
    paths = {err.path for err in result.errors}
    assert str(goals / "bad-a.md") in paths
    assert str(goals / "bad-b.md") in paths
