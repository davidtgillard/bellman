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
    assert (pdir / "work-packages.yaml").is_file()


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


def test_delete_by_name_ambiguous_when_same_name(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    with pytest.raises(BellmanLayoutError, match="ambiguous name"):
        layout.delete_entity(tmp_path, "system-mci")


def test_delete_by_path_disambiguates_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    layout.delete_entity(tmp_path, "goals/system-mci.md")
    assert not layout.goal_path(tmp_path, "system-mci").exists()
    assert layout.initiative_path(tmp_path, "system-mci").exists()


def test_delete_by_path_disambiguates_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    layout.delete_entity(tmp_path, "initiatives/system-mci.md")
    assert layout.goal_path(tmp_path, "system-mci").exists()
    assert not layout.initiative_path(tmp_path, "system-mci").exists()


def test_delete_project_by_path(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "foo")
    layout.delete_entity(tmp_path, "projects/foo")
    assert not layout.project_dir(tmp_path, "foo").exists()


def test_delete_rejects_path_traversal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with pytest.raises(BellmanLayoutError, match="invalid entity path"):
        layout.delete_entity(tmp_path, "goals/../../etc/passwd")
