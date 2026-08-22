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


def test_rename_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "old-goal")
    renamed = layout.rename_entity(tmp_path, "old-goal", "new-goal")
    assert renamed.kind == "goal"
    assert renamed.old_name == "old-goal"
    assert renamed.new_name == "new-goal"
    assert layout.goal_path(tmp_path, "new-goal").is_file()
    assert not layout.goal_path(tmp_path, "old-goal").exists()
    assert (
        layout.goal_path(tmp_path, "new-goal")
        .read_text(encoding="utf-8")
        .startswith("# New Goal")
    )


def test_rename_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "old-init")
    renamed = layout.rename_entity(tmp_path, "old-init", "new-init")
    assert renamed.kind == "initiative"
    assert layout.initiative_path(tmp_path, "new-init").is_file()


def test_rename_milestone(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_milestone(tmp_path, "old-ms")
    renamed = layout.rename_entity(tmp_path, "old-ms", "new-ms")
    assert renamed.kind == "milestone"
    assert layout.milestone_path(tmp_path, "new-ms").is_file()


def test_rename_project(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "old-proj")
    renamed = layout.rename_entity(tmp_path, "old-proj", "new-proj")
    assert renamed.kind == "project"
    assert layout.project_dir(tmp_path, "new-proj").is_dir()
    assert layout.project_md_path(tmp_path, "new-proj").is_file()
    assert not layout.project_dir(tmp_path, "old-proj").exists()


def test_rename_destination_exists(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "keep-me")
    layout.create_goal(tmp_path, "move-me")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.rename_entity(tmp_path, "move-me", "keep-me")


def test_rename_by_name_ambiguous_when_same_name(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    with pytest.raises(BellmanLayoutError, match="ambiguous name"):
        layout.rename_entity(tmp_path, "system-mci", "renamed")


def test_rename_by_kind_disambiguates(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    renamed = layout.rename_entity(
        tmp_path,
        "system-mci",
        "goal-renamed",
        kind="goal",
    )
    assert renamed.kind == "goal"
    assert layout.goal_path(tmp_path, "goal-renamed").is_file()
    assert layout.initiative_path(tmp_path, "system-mci").is_file()


def test_rename_by_path_disambiguates_goal(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    renamed = layout.rename_entity(tmp_path, "goals/system-mci.md", "goal-renamed")
    assert renamed.kind == "goal"
    assert layout.goal_path(tmp_path, "goal-renamed").is_file()


def test_rename_rewrites_scope_dependency(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "old-dep")
    layout.create_initiative(tmp_path, "follower")
    initiative = layout.initiative_path(tmp_path, "follower")
    initiative.write_text(
        initiative.read_text(encoding="utf-8") + "- old-dep [FS, Mandatory]\n",
        encoding="utf-8",
    )
    layout.rename_entity(tmp_path, "old-dep", "new-dep")
    text = initiative.read_text(encoding="utf-8")
    assert "- new-dep [FS, Mandatory]" in text
    assert "old-dep" not in text


def test_rename_project_rewrites_cross_project_wp_ref(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "old-proj")
    layout.create_project(tmp_path, "consumer")
    wp_path = layout.work_packages_path(tmp_path, "consumer")
    wp_path.write_text(
        """version: 1

work_packages:
  - title: Do Thing
    dependencies:
      - old-proj/wp-slug [FS, Mandatory]
""",
        encoding="utf-8",
    )
    layout.rename_entity(tmp_path, "old-proj", "new-proj", kind="project")
    text = wp_path.read_text(encoding="utf-8")
    assert "new-proj/wp-slug [FS, Mandatory]" in text
    assert "old-proj/wp-slug" not in text
