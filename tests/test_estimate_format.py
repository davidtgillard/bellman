"""Plaintext and JSON formatting tests."""

from __future__ import annotations

from bellman.estimate.format import format_estimate_json, format_estimate_text
from bellman.estimate.simulate import estimate_project
from bellman.model import Project, ThreePointEstimate, WorkPackage


def _project() -> Project:
    return Project(
        name="demo",
        title="Demo",
        path="projects/demo/demo.md",
        introduction="i",
        motivation="m",
        detailed_description="d",
        criteria_for_success="ok",
        work_packages=(
            WorkPackage(
                slug="a",
                title="a",
                description="d",
                estimate=ThreePointEstimate(1.0, 1.0, 1.0, "w"),
            ),
        ),
    )


def test_format_text_includes_seed() -> None:
    estimate = estimate_project(_project(), trials=3, seed=9)
    text = format_estimate_text(estimate)
    assert "Seed: 9\n" in text
    assert "Unit: w\n" in text


def test_format_text_omits_seed_when_missing() -> None:
    estimate = estimate_project(_project(), trials=3)
    assert "Seed:" not in format_estimate_text(estimate)


def test_format_json_trailing_newline() -> None:
    estimate = estimate_project(_project(), trials=3, seed=1)
    text = format_estimate_json(estimate)
    assert text.endswith("\n")
    assert '"schema_version": "1.0.0"' in text
