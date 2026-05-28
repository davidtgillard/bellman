"""Validation tests."""

from __future__ import annotations

from pathlib import Path

from snark.roadmap import load
from snark.validate import validate_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_example_roadmap_validates() -> None:
    roadmap = load(EXAMPLES)
    errors = validate_roadmap(roadmap)
    assert errors == []
