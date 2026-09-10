"""CLI tests for the status subcommand."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyfits.result import Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app
from bellman.graph.delta import RegistryDelta
from bellman.graph.desired import DesiredNode

runner = CliRunner()

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_status_example_roadmap_exit_zero() -> None:
    result = runner.invoke(app, ["status", "--no-registry", str(EXAMPLES)])
    assert result.exit_code == 0
    assert "explore-ml-ranking" in result.output
    assert "billing-redesign" in result.output
    assert "reduce-churn" in result.output
    assert "Summary:" in result.output


def test_status_invalid_markdown_still_exit_zero(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    goals = tmp_path / "goals"
    goals.mkdir(parents=True, exist_ok=True)
    (goals / "bad-goal.md").write_text("# Wrong Title\n\nContent.\n", encoding="utf-8")
    result = runner.invoke(app, ["status", "--no-registry", str(tmp_path)])
    assert result.exit_code == 0
    assert "invalid" in result.output
    assert "bad-goal" in result.output


def test_status_does_not_sync(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch("bellman.cli.sync_roadmap") as sync_mock:
        result = runner.invoke(app, ["status", "--no-registry", str(tmp_path)])
    sync_mock.assert_not_called()
    assert result.exit_code == 0


def test_status_registry_delta_exit_zero(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    (tmp_path / "goals" / "manual-goal.md").write_text(
        "# Manual Goal\n\nAdded by hand.\n",
        encoding="utf-8",
    )
    delta = RegistryDelta(
        missing_nodes=("goal manual-goal",),
        extra_nodes=(),
        missing_links=(),
        extra_links=(),
        missing_node_ids=frozenset({DesiredNode("goal", "goal/manual-goal")}),
        desired_node_count=1,
        actual_node_count=0,
    )
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Ok(delta),
    ):
        result = runner.invoke(app, ["status", str(tmp_path)])
    assert result.exit_code == 0
    assert "registry: missing" in result.output
    assert "goal manual-goal" in result.output


def test_status_exits_one_on_hard_registry_failure(tmp_path: Path) -> None:
    from pyfits.result import Err

    from bellman.graph.delta import RegistryDeltaError

    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Err(RegistryDeltaError("unreadable registry")),
    ):
        result = runner.invoke(app, ["status", str(tmp_path)])
    assert result.exit_code == 1
    assert "Status failed" in result.output
    assert "unreadable registry" in result.output
