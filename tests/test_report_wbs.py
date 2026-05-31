"""WBS report tests."""

from __future__ import annotations

import csv
from dataclasses import replace
from io import StringIO
from pathlib import Path

from typer.testing import CliRunner

from bellman.cli import app
from bellman.model import ThreePointEstimate, WorkPackage
from bellman.report.wbs import (
    WBS_HEADERS,
    _estimate_columns,
    iter_wbs_rows,
    write_wbs_csv,
)
from bellman.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"
runner = CliRunner()


def _read_csv(text: str) -> list[list[str]]:
    return list(csv.reader(StringIO(text)))


def test_wbs_headers_and_example_roadmap() -> None:
    roadmap = load(EXAMPLES)
    buffer = StringIO()
    write_wbs_csv(roadmap, buffer)
    rows = _read_csv(buffer.getvalue())
    assert rows[0] == list(WBS_HEADERS)
    assert len(rows) == 3
    assert rows[1][0] == "billing-redesign/wp-invoicing"
    assert rows[1][1] == "1"
    assert rows[1][2] == "wp-invoicing"
    assert rows[1][5:] == ["", "", "", ""]
    assert rows[2][0] == "billing-redesign/wp-pdf-export"
    assert rows[2][1] == "1.1"
    assert rows[2][2] == "  wp-pdf-export"


def test_wbs_orders_siblings_alphabetically(tmp_path: Path) -> None:
    yaml_text = """\
version: 1

work_packages:
  - title: wp-zulu
    description: Last alphabetically.
    estimate: unknown
  - title: wp-alpha
    description: First alphabetically.
    estimate: unknown
  - title: wp-mike
    description: Middle alphabetically.
    sub_packages:
      - title: wp-zed-child
        description: Child b.
        estimate: unknown
      - title: wp-ace-child
        description: Child a.
        estimate: unknown
"""
    project_dir = tmp_path / "projects" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "demo.md").write_text(
        "# Demo\n\n## Introduction\n\nIntro.\n\n## Motivation\n\nWhy.\n\n"
        "## Detailed Description\n\nDetails.\n\n## Criteria for Success\n\nDone.\n",
        encoding="utf-8",
    )
    wp_path = project_dir / "work-packages.yaml"
    wp_path.write_text(yaml_text, encoding="utf-8")
    roadmap = load(tmp_path)
    rows = list(iter_wbs_rows(roadmap))
    assert [row[0] for row in rows] == [
        "demo/wp-alpha",
        "demo/wp-mike",
        "demo/wp-ace-child",
        "demo/wp-zed-child",
        "demo/wp-zulu",
    ]
    assert [row[1] for row in rows] == ["1", "2", "2.1", "2.2", "3"]
    assert [row[2] for row in rows] == [
        "wp-alpha",
        "wp-mike",
        "  wp-ace-child",
        "  wp-zed-child",
        "wp-zulu",
    ]


def test_wbs_unknown_estimate_columns_are_empty() -> None:
    assert _estimate_columns(None) == ("", "", "", "")
    assert _estimate_columns(ThreePointEstimate(1.0, 2.0, 3.0, "w")) != (
        "",
        "",
        "",
        "",
    )


def test_wbs_pert_uses_three_point_formula() -> None:
    estimate = ThreePointEstimate(
        optimistic=1.0,
        most_likely=2.0,
        pessimistic=7.0,
        unit="d",
    )
    wp = WorkPackage(
        slug="pert-demo",
        title="pert-demo",
        description="PERT check.",
        estimate=estimate,
    )
    project = load(EXAMPLES).project_by_name("billing-redesign")
    assert project is not None
    project = replace(project, work_packages=(wp,))
    roadmap = replace(load(EXAMPLES), projects=(project,))
    row = next(iter(iter_wbs_rows(roadmap)))
    assert row[5:] == ["7d", "2d", "1d", "2.67d"]


def test_report_wbs_cli_writes_file(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["report", "wbs", str(EXAMPLES), "-o", str(tmp_path / "out.csv")],
    )
    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    rows = _read_csv((tmp_path / "out.csv").read_text(encoding="utf-8"))
    assert rows[0] == list(WBS_HEADERS)
    assert len(rows) == 3


def test_report_wbs_cli_unknown_project(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            str(EXAMPLES),
            "--project",
            "missing-project",
            "-o",
            str(tmp_path / "out.csv"),
        ],
    )
    assert result.exit_code == 1
    assert "project not found" in result.stderr


def test_report_wbs_cli_writes_stdout_by_default() -> None:
    result = runner.invoke(app, ["report", "wbs", str(EXAMPLES)])
    assert result.exit_code == 0
    assert "Wrote" not in result.stdout
    rows = _read_csv(result.stdout)
    assert rows[0] == list(WBS_HEADERS)
    assert len(rows) == 3
