"""CLI and JSON schema tests for ``bellman estimate``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app
from bellman.estimate import SCHEMA_VERSION, load_estimate_schema
from bellman.estimate.format import estimate_to_dict
from bellman.estimate.simulate import estimate_project
from bellman.model import Project, Roadmap, ThreePointEstimate, WorkPackage

runner = CliRunner()

_WP_YAML = """version: 1

work_packages:
  - title: wp-alpha
    description: First leaf.
    estimate: [2w, 2w, 2w]
  - title: wp-beta
    description: Second leaf.
    estimate: [2w, 2w, 2w]
"""


def _roadmap_with_project(tmp_path: Path) -> Path:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    layout.create_project(tmp_path, "demo-proj")
    wp = tmp_path / "projects" / "demo-proj" / "work-packages.yaml"
    wp.write_text(_WP_YAML, encoding="utf-8")
    return tmp_path


def test_schema_version_matches_constant() -> None:
    schema = load_estimate_schema()
    assert schema["x-schema-version"] == SCHEMA_VERSION
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def test_estimate_json_matches_schema() -> None:
    project = Project(
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
                estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
            ),
        ),
    )
    estimate = estimate_project(project, trials=4, seed=1)
    Draft202012Validator(load_estimate_schema()).validate(estimate_to_dict(estimate))


def test_cli_plaintext(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            [
                "estimate",
                "demo-proj",
                "--path",
                str(root),
                "--seed",
                "1",
                "--trials",
                "20",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "Project: demo-proj" in result.stdout
    assert "Expected effort:" in result.stdout
    assert "Expected duration:" in result.stdout
    assert "Num people: 1" in result.stdout
    assert "Parallel fraction: 0.70" in result.stdout


def test_cli_json_validates(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            [
                "estimate",
                "demo-proj",
                "--path",
                str(root),
                "--json",
                "--seed",
                "1",
                "--trials",
                "20",
                "--num-people",
                "2",
            ],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    Draft202012Validator(load_estimate_schema()).validate(payload)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["num_people"] == 2
    assert payload["method"] == "amdahl-cpm"
    assert payload["scheduler"] == "list-scheduling"


def test_cli_no_roadmap(tmp_path: Path) -> None:
    result = runner.invoke(app, ["estimate", "demo", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "no initialized bellman roadmap" in result.output


def test_cli_load_oserror(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with (
        patch("bellman.cli.libfits_available", return_value=False),
        patch("bellman.cli.load", side_effect=OSError("disk")),
    ):
        result = runner.invoke(
            app,
            ["estimate", "demo-proj", "--path", str(root)],
        )
    assert result.exit_code == 1
    assert "load error: disk" in result.output


def test_cli_project_missing_from_roadmap(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with (
        patch("bellman.cli.libfits_available", return_value=False),
        patch(
            "bellman.cli.load",
            return_value=Roadmap(root=str(root)),
        ),
    ):
        result = runner.invoke(
            app,
            ["estimate", "demo-proj", "--path", str(root)],
        )
    assert result.exit_code == 1
    assert "project not found" in result.output


def test_cli_unknown_project(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["estimate", "missing", "--path", str(root)],
        )
    assert result.exit_code == 1
    assert "missing" in result.output


def test_cli_bad_parallel_fraction(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            [
                "estimate",
                "demo-proj",
                "--path",
                str(root),
                "--parallel-fraction",
                "1.5",
            ],
        )
    assert result.exit_code == 1
    assert "parallel-fraction" in result.output


def test_cli_empty_work_packages(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    wp = root / "projects" / "demo-proj" / "work-packages.yaml"
    wp.write_text("version: 1\n\nwork_packages: []\n", encoding="utf-8")
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["estimate", "demo-proj", "--path", str(root)],
        )
    assert result.exit_code == 1
    assert "no work packages" in result.output


def test_cli_unknown_estimate(tmp_path: Path) -> None:
    root = _roadmap_with_project(tmp_path)
    wp = root / "projects" / "demo-proj" / "work-packages.yaml"
    wp.write_text(
        "version: 1\n\nwork_packages:\n  - title: wp-a\n    description: A.\n"
        "    estimate: unknown\n",
        encoding="utf-8",
    )
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(
            app,
            ["estimate", "demo-proj", "--path", str(root)],
        )
    assert result.exit_code == 1
    assert "unknown estimate" in result.output


def test_load_schema_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Missing:
        def joinpath(self, _name: str) -> _Missing:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            raise FileNotFoundError("gone")

    monkeypatch.setattr("bellman.estimate.schema.files", lambda _name: _Missing())
    with pytest.raises(FileNotFoundError, match="not installed"):
        load_estimate_schema()


def test_load_schema_not_object(monkeypatch: pytest.MonkeyPatch) -> None:
    class _List:
        def joinpath(self, _name: str) -> _List:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            return "[1, 2]"

    monkeypatch.setattr("bellman.estimate.schema.files", lambda _name: _List())
    with pytest.raises(ValueError, match="JSON object"):
        load_estimate_schema()


def test_load_schema_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Bad:
        def joinpath(self, _name: str) -> _Bad:
            return self

        def read_text(self, encoding: str = "utf-8") -> str:
            return "{not json"

    monkeypatch.setattr("bellman.estimate.schema.files", lambda _name: _Bad())
    with pytest.raises(ValueError, match="not valid JSON"):
        load_estimate_schema()
