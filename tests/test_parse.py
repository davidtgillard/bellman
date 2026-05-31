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
    assert wps[0].title == "wp-invoicing"
    assert len(wps[0].sub_packages) == 1


def test_parse_work_packages_file() -> None:
    wp_path = EXAMPLES / "projects" / "billing-redesign" / "work-packages.yaml"
    packages = parse_work_packages(wp_path, project_name="billing-redesign")
    assert packages[0].sub_packages[0].slug == "wp-pdf-export"
    assert packages[0].sub_packages[0].title == "wp-pdf-export"
    assert isinstance(packages[0].sub_packages[0].estimate, ThreePointEstimate)


def test_parse_unknown_estimate() -> None:
    assert _parse_estimate_value("unknown", "path", "wp") is UNKNOWN_ESTIMATE
    assert _parse_estimate_value("Unknown", "path", "wp") is UNKNOWN_ESTIMATE


def test_parse_full_estimate() -> None:
    raw = {
        "optimistic": "1w",
        "most_likely": "2w",
        "pessimistic": "3w",
    }
    est = _parse_estimate_value(raw, "path", "wp")
    assert isinstance(est, ThreePointEstimate)
    assert est.optimistic == 1.0
    assert est.most_likely == 2.0
    assert est.pessimistic == 3.0
    assert est.unit == "w"


def test_parse_mixed_duration_suffixes_fails() -> None:
    raw = {
        "optimistic": "1w",
        "most_likely": "2d",
        "pessimistic": "3w",
    }
    with pytest.raises(ValueError, match="same duration suffix"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_rejects_unit_field() -> None:
    raw = {
        "optimistic": "1w",
        "most_likely": "2w",
        "pessimistic": "3w",
        "unit": "weeks",
    }
    with pytest.raises(ValueError, match="must not include unit"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_requires_suffix() -> None:
    raw = {"optimistic": 1, "most_likely": "2w", "pessimistic": "3w"}
    with pytest.raises(ValueError, match="must be a duration with h, d, or w suffix"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_estimate_allows_equal_values() -> None:
    raw = {
        "optimistic": "2w",
        "most_likely": "2w",
        "pessimistic": "2w",
    }
    est = _parse_estimate_value(raw, "path", "wp")
    assert isinstance(est, ThreePointEstimate)
    assert est.optimistic == est.most_likely == est.pessimistic == 2.0


def test_parse_estimate_rejects_out_of_order_values() -> None:
    raw = {
        "optimistic": "7w",
        "most_likely": "2w",
        "pessimistic": "1w",
    }
    with pytest.raises(
        ValueError,
        match="optimistic <= most_likely <= pessimistic",
    ):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_partial_estimate_fails() -> None:
    raw = {"optimistic": "1w", "most_likely": "2w"}
    with pytest.raises(ValueError, match="incomplete estimate"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_partial_unknown_in_estimate_fails() -> None:
    raw = {
        "optimistic": "unknown",
        "most_likely": "2w",
        "pessimistic": "3w",
    }
    with pytest.raises(ValueError, match="partial estimate with unknown"):
        _parse_estimate_value(raw, "path", "wp")


def test_parse_invalid_estimate_body_fails() -> None:
    with pytest.raises(ValueError, match="must be unknown or a complete"):
        _parse_estimate_value("TBD", "path", "wp")


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
