"""Parser tests."""

from __future__ import annotations

from pathlib import Path

from snark.parse.dependencies import parse_dependencies_section
from snark.parse.work_packages import parse_work_packages
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
    assert packages[0].children[0].estimate is not None
