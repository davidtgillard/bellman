"""Tests for precedence dependency reports."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from bellman import layout
from bellman.report.dependencies import write_dependencies_report
from bellman.roadmap import load


def _seed_roadmap(root: Path) -> None:
    layout.ensure_roadmap_dirs(root)
    layout.create_initiative(root, "alpha")
    layout.create_initiative(root, "beta")
    beta = layout.initiative_path(root, "beta")
    beta.write_text(
        beta.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- alpha [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    layout.create_project(root, "demo")
    wp_path = layout.work_packages_path(root, "demo")
    wp_path.write_text(
        """version: 1

work_packages:
  - title: first
    description: TBD.
  - title: second
    description: TBD.
    dependencies:
      - predecessor: first
""",
        encoding="utf-8",
    )


def test_report_all_dependencies(tmp_path: Path) -> None:
    _seed_roadmap(tmp_path)
    roadmap = load(tmp_path)
    out = StringIO()
    write_dependencies_report(roadmap, out)
    text = out.getvalue()
    assert "alpha -> beta [FS, Mandatory]" in text
    assert "first -> demo/second [FS, Mandatory]" in text


def test_report_entity_predecessors_and_successors(tmp_path: Path) -> None:
    _seed_roadmap(tmp_path)
    roadmap = load(tmp_path)
    out = StringIO()
    write_dependencies_report(roadmap, out, entity="alpha")
    text = out.getvalue()
    assert "Predecessors:" in text
    assert "Successors:" in text
    assert "(none)" in text.split("Predecessors:")[1].split("Successors:")[0]
    assert "alpha -> beta [FS, Mandatory]" in text.split("Successors:")[1]
