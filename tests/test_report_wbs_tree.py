"""WBS tree report tests."""

from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bellman.cli import app
from bellman.model import ThreePointEstimate, WorkPackage
from bellman.report.wbs import pert_numeric
from bellman.report.wbs_tree import (
    project_total_pert,
    rollup,
    write_wbs_tree,
)
from bellman.roadmap import load

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"
runner = CliRunner()


def test_rollup_leaf_pert_formula() -> None:
    estimate = ThreePointEstimate(
        optimistic=1.0,
        most_likely=2.0,
        pessimistic=7.0,
        unit="d",
    )
    wp = WorkPackage(
        slug="leaf",
        title="leaf",
        description="Leaf.",
        estimate=estimate,
    )
    result = rollup(wp)
    assert result.pert == pytest.approx(pert_numeric(estimate))
    assert result.display == "2.67d"


def test_rollup_parent_sums_children() -> None:
    child_a = WorkPackage(
        slug="a",
        title="a",
        description="A.",
        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
    )
    child_b = WorkPackage(
        slug="b",
        title="b",
        description="B.",
        estimate=ThreePointEstimate(2.0, 2.0, 2.0, "d"),
    )
    parent = WorkPackage(
        slug="parent",
        title="parent",
        description="Parent.",
        sub_packages=(child_a, child_b),
    )
    result = rollup(parent)
    assert result.pert == pytest.approx(3.0)
    assert result.display == "3d"


def test_rollup_unknown_child_marks_parent_unknown() -> None:
    from bellman.model import UNKNOWN_ESTIMATE

    child = WorkPackage(
        slug="child",
        title="child",
        description="Child.",
        estimate=UNKNOWN_ESTIMATE,
    )
    parent = WorkPackage(
        slug="parent",
        title="parent",
        description="Parent.",
        sub_packages=(child,),
    )
    assert rollup(parent).display == "?"
    assert rollup(parent).pert is None


def test_rollup_mixed_units_raises() -> None:
    child_a = WorkPackage(
        slug="a",
        title="a",
        description="A.",
        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
    )
    child_b = WorkPackage(
        slug="b",
        title="b",
        description="B.",
        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "w"),
    )
    parent = WorkPackage(
        slug="parent",
        title="parent",
        description="Parent.",
        sub_packages=(child_a, child_b),
    )
    with pytest.raises(ValueError, match="mixed duration units"):
        rollup(parent)


def test_billing_redesign_tree_output() -> None:
    roadmap = load(EXAMPLES)
    buffer = StringIO()
    write_wbs_tree(roadmap, buffer, project_name="billing-redesign")
    text = buffer.getvalue()
    assert "project: billing-redesign\n" in text
    assert text.count("total estimate: 2.17w\n") == 2
    assert "wp-invoicing  2.17w" in text
    assert "wp-pdf-export  2.17w" in text


def test_project_total_matches_root_rollup() -> None:
    project = load(EXAMPLES).project_by_name("billing-redesign")
    assert project is not None
    total = project_total_pert(project)
    assert total.display == "2.17w"


def test_report_wbs_tree_cli() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            "tree",
            "--project",
            "billing-redesign",
            str(EXAMPLES),
        ],
    )
    assert result.exit_code == 0
    assert result.stdout.count("total estimate: 2.17w") == 2
    assert "wp-invoicing" in result.stdout


def test_report_wbs_tree_cli_unknown_project() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            "tree",
            "--project",
            "missing-project",
            str(EXAMPLES),
        ],
    )
    assert result.exit_code == 1
    assert "project not found" in result.stderr


def test_report_wbs_tree_cli_without_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roadmap = tmp_path / "roadmap"
    shutil.copytree(EXAMPLES, roadmap, dirs_exist_ok=True)
    monkeypatch.chdir(roadmap)
    result = runner.invoke(
        app,
        [
            "report",
            "wbs",
            "tree",
            "--project",
            "billing-redesign",
        ],
    )
    assert result.exit_code == 0
    assert result.stdout.count("total estimate: 2.17w") == 2
    assert "wp-invoicing" in result.stdout


def test_report_wbs_csv_still_works() -> None:
    result = runner.invoke(app, ["report", "wbs", str(EXAMPLES)])
    assert result.exit_code == 0
    assert "work package,numbered section" in result.stdout
