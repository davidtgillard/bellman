"""Roadmap-level behaviour of attributes: init, optional directory, loading."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

from attr_support import (
    PRIORITY_JSONC,
    make_root,
    write_attribute,
    write_initiative,
    write_milestone,
    write_project,
)
from typer.testing import CliRunner

from bellman import layout
from bellman.cli import app
from bellman.roadmap import load, load_for_validation

runner = CliRunner()


def test_init_creates_empty_attributes_directory(tmp_path: Path) -> None:
    with patch("bellman.cli.libfits_available", return_value=False):
        result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "attributes").is_dir()
    assert list((tmp_path / "attributes").iterdir()) == []


def test_roadmap_without_attributes_directory_loads_and_validates(
    tmp_path: Path,
) -> None:
    root = make_root(tmp_path)
    shutil.rmtree(root / layout.ATTRIBUTES_DIR)
    write_initiative(root, "alpha")
    roadmap = load(root)
    assert len(roadmap.attributes) == 0
    result = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert result.exit_code == 0, result.output


def test_unused_catalog_does_not_affect_existing_roadmap(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_initiative(root, "alpha")
    assert "priority" not in load(root).attributes
    write_attribute(root, "priority", PRIORITY_JSONC)
    assert "priority" in load(root).attributes


def test_classifications_load_on_every_kind(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_initiative(root, "i", ["priority: P1"])
    write_project(root, "p", ["priority: P0"])
    write_milestone(root, "m", ["priority: P2"])
    roadmap = load(root)
    assert roadmap.initiatives[0].classifications[0].value == "P1"
    assert roadmap.projects[0].classifications[0].value == "P0"
    assert roadmap.milestones[0].classifications[0].value == "P2"


def test_milestone_description_excludes_classifications(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_milestone(root, "ga", ["priority: P1"])
    description = load(root).milestones[0].description
    assert "Classifications" not in description
    assert "priority" not in description


def test_bad_classification_line_is_a_load_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    path = write_initiative(root, "alpha", ["priority: P1"])
    path.write_text(
        path.read_text(encoding="utf-8") + "- not valid\n", encoding="utf-8"
    )
    result = load_for_validation(root)
    assert result.errors
    assert any("alpha" in e.path or "alpha" in e.message for e in result.errors)
