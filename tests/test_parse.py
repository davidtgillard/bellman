"""Parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from snark.model import UNKNOWN_ESTIMATE, ThreePointEstimate
from snark.parse.dependencies import parse_dependencies_section
from snark.parse.work_packages import _parse_estimate, parse_work_packages
from snark.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_parse_dependencies() -> None:
    body = "- after: foo [FS, Mandatory]\n"
    edges = parse_dependencies_section(body, successor="bar")
    assert len(edges) == 1
    assert edges[0].predecessor == "foo"
    assert edges[0].successor == "bar"


def test_load_example_roadmap() -> None:
    roadmap = load(EXAMPLES)
    assert len(roadmap.initiatives) == 1
    assert len(roadmap.projects) == 1
    assert roadmap.project_by_name("billing-redesign") is not None
    wps = roadmap.project_by_name("billing-redesign").work_packages  # type: ignore[union-attr]
    assert len(wps) == 1
    assert wps[0].slug == "wp-invoicing"
    assert len(wps[0].children) == 1


def test_parse_work_packages_file() -> None:
    wp_path = EXAMPLES / "projects" / "billing-redesign" / "work-packages.md"
    packages = parse_work_packages(wp_path, project_name="billing-redesign")
    assert packages[0].children[0].slug == "wp-pdf-export"
    assert isinstance(packages[0].children[0].estimate, ThreePointEstimate)


def test_parse_unknown_estimate() -> None:
    assert _parse_estimate("unknown", "path", "wp") is UNKNOWN_ESTIMATE
    assert _parse_estimate("Unknown", "path", "wp") is UNKNOWN_ESTIMATE


def test_parse_full_estimate() -> None:
    body = "- optimistic: 1\n- most likely: 2\n- pessimistic: 3\n- unit: weeks\n"
    est = _parse_estimate(body, "path", "wp")
    assert isinstance(est, ThreePointEstimate)
    assert est.optimistic == 1.0
    assert est.most_likely == 2.0
    assert est.pessimistic == 3.0
    assert est.unit == "weeks"


def test_parse_partial_estimate_fails() -> None:
    body = "- optimistic: 1\n- most likely: 2\n"
    with pytest.raises(ValueError, match="incomplete estimate"):
        _parse_estimate(body, "path", "wp")


def test_parse_partial_unknown_in_estimate_fails() -> None:
    body = "- optimistic: unknown\n- most likely: 2\n- pessimistic: 3\n- unit: weeks\n"
    with pytest.raises(ValueError, match="partial estimate with unknown"):
        _parse_estimate(body, "path", "wp")


def test_parse_invalid_estimate_body_fails() -> None:
    with pytest.raises(ValueError, match="must be unknown or a complete"):
        _parse_estimate("TBD", "path", "wp")
