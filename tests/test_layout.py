"""Layout and CLI filesystem tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bellman import layout
from bellman.errors import BellmanLayoutError


def test_find_roadmap_root_from_subfolder(tmp_path: Path) -> None:
    roadmap = tmp_path / "roadmap"
    subfolder = roadmap / "projects" / "billing-redesign"
    subfolder.mkdir(parents=True)
    (roadmap / ".fits").mkdir()
    assert layout.find_roadmap_root(subfolder) == roadmap.resolve()


def test_find_roadmap_root_stops_at_git_root(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    git_root = outer / "repo"
    subfolder = git_root / "projects" / "billing-redesign"
    subfolder.mkdir(parents=True)
    (outer / ".fits").mkdir()
    (git_root / ".git").mkdir()
    assert layout.find_roadmap_root(subfolder) is None


def test_discover_roadmap_root_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(BellmanLayoutError, match="no initialized bellman roadmap"):
        layout.discover_roadmap_root(tmp_path)


def test_create_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    path = layout.create_initiative(tmp_path, "my-initiative")
    assert path.is_file()
    assert "Introduction" in path.read_text(encoding="utf-8")


def test_create_project(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    pdir = layout.create_project(tmp_path, "my-project")
    assert (pdir / "my-project.md").is_file()
    assert (pdir / "work-packages.md").is_file()


def test_promote_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "grow-feature")
    layout.promote_initiative(tmp_path, "grow-feature")
    assert layout.project_dir(tmp_path, "grow-feature").is_dir()
    assert layout.archived_initiative_path(tmp_path, "grow-feature").is_file()
    assert not layout.initiative_path(tmp_path, "grow-feature").exists()


def test_create_project_rejects_md_suffix(tmp_path: Path) -> None:
    with pytest.raises(BellmanLayoutError, match="cannot be created"):
        layout.create_project(tmp_path, "foo.md")
