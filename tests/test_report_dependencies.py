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


def test_report_entity_via_fqn_matches_name(tmp_path: Path) -> None:
    _seed_roadmap(tmp_path)
    roadmap = load(tmp_path)
    by_name = StringIO()
    by_fqn = StringIO()
    write_dependencies_report(roadmap, by_name, entity="alpha")
    write_dependencies_report(
        roadmap,
        by_fqn,
        entity=layout.resolve_entity_filter(tmp_path, "initiatives/alpha"),
    )
    assert by_name.getvalue() == by_fqn.getvalue()


def test_report_deps_cli_accepts_fqn_and_wp_id(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from bellman.cli import app

    _seed_roadmap(tmp_path)
    (tmp_path / ".fits").mkdir()
    runner = CliRunner()
    fqn = runner.invoke(
        app,
        ["report", "deps", "initiatives/alpha", "--path", str(tmp_path)],
    )
    assert fqn.exit_code == 0
    assert "alpha -> beta [FS, Mandatory]" in fqn.stdout

    wp = runner.invoke(
        app,
        ["report", "deps", "demo/second", "--path", str(tmp_path)],
    )
    assert wp.exit_code == 0
    assert "first -> demo/second [FS, Mandatory]" in wp.stdout

    missing = runner.invoke(
        app,
        ["report", "deps", "initiatives/missing", "--path", str(tmp_path)],
    )
    assert missing.exit_code == 1
    assert "no entity" in missing.output
