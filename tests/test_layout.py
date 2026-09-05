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


def test_demote_parks_project_folder_and_restores_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "grow-feature")
    original = layout.initiative_path(tmp_path, "grow-feature").read_text(
        encoding="utf-8"
    )
    layout.promote_initiative(tmp_path, "grow-feature")
    sidecar = layout.project_dir(tmp_path, "grow-feature") / "notes.txt"
    sidecar.write_text("keep me\n", encoding="utf-8")
    wp_path = layout.work_packages_path(tmp_path, "grow-feature")
    wp_path.write_text(
        "version: 1\n\nwork_packages:\n  - title: wp-a\n    description: TBD.\n",
        encoding="utf-8",
    )

    restored = layout.demote_project(tmp_path, "grow-feature")

    assert restored == layout.initiative_path(tmp_path, "grow-feature")
    assert restored.read_text(encoding="utf-8") == original
    assert not layout.project_dir(tmp_path, "grow-feature").exists()
    stash = layout.archived_project_dir(tmp_path, "grow-feature")
    assert stash.is_dir()
    assert (stash / "notes.txt").read_text(encoding="utf-8") == "keep me\n"
    assert "wp-a" in (stash / "work-packages.yaml").read_text(encoding="utf-8")
    assert not layout.archived_initiative_path(tmp_path, "grow-feature").exists()


def test_demote_never_promoted_project_synthesizes_initiative(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "from-scratch")
    project_md = layout.project_md_path(tmp_path, "from-scratch").read_text(
        encoding="utf-8"
    )
    restored = layout.demote_project(tmp_path, "from-scratch")
    assert restored.read_text(encoding="utf-8") == project_md
    assert layout.archived_project_dir(tmp_path, "from-scratch").is_dir()


def test_promote_restores_archived_project_folder(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "grow-feature")
    layout.promote_initiative(tmp_path, "grow-feature")
    (layout.project_dir(tmp_path, "grow-feature") / "notes.txt").write_text(
        "keep me\n", encoding="utf-8"
    )
    layout.demote_project(tmp_path, "grow-feature")
    restored = layout.promote_initiative(tmp_path, "grow-feature")
    assert restored == layout.project_dir(tmp_path, "grow-feature")
    assert (restored / "notes.txt").read_text(encoding="utf-8") == "keep me\n"
    assert not layout.archived_project_dir(tmp_path, "grow-feature").exists()
    assert layout.archived_initiative_path(tmp_path, "grow-feature").is_file()


def test_demote_errors(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with pytest.raises(BellmanLayoutError, match="project not found"):
        layout.demote_project(tmp_path, "missing")
    layout.create_initiative(tmp_path, "clash")
    layout.create_project(tmp_path, "clash")
    with pytest.raises(BellmanLayoutError, match="initiative already exists"):
        layout.demote_project(tmp_path, "clash")


def test_rename_initiative_renames_archived_project_stash(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "old-init")
    layout.promote_initiative(tmp_path, "old-init")
    (layout.project_dir(tmp_path, "old-init") / "notes.txt").write_text(
        "keep\n", encoding="utf-8"
    )
    layout.demote_project(tmp_path, "old-init")
    layout.rename_entity(tmp_path, "old-init", "new-init")
    assert layout.initiative_path(tmp_path, "new-init").is_file()
    stash = layout.archived_project_dir(tmp_path, "new-init")
    assert stash.is_dir()
    assert (stash / "new-init.md").is_file()
    assert (stash / "notes.txt").read_text(encoding="utf-8") == "keep\n"
    assert not layout.archived_project_dir(tmp_path, "old-init").exists()


def test_delete_initiative_removes_archived_project_stash(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "to-delete")
    layout.promote_initiative(tmp_path, "to-delete")
    layout.demote_project(tmp_path, "to-delete")
    layout.delete_entity(tmp_path, "to-delete")
    assert not layout.initiative_path(tmp_path, "to-delete").exists()
    assert not layout.archived_project_dir(tmp_path, "to-delete").exists()


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


def test_create_duplicate_entities(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "dup-init")
    layout.create_project(tmp_path, "dup-proj")
    layout.create_milestone(tmp_path, "dup-ms")
    layout.create_goal(tmp_path, "dup-goal")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.create_initiative(tmp_path, "dup-init")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.create_project(tmp_path, "dup-proj")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.create_milestone(tmp_path, "dup-ms")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.create_goal(tmp_path, "dup-goal")


def test_resolve_entity_path_matrix(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "g1")
    layout.create_milestone(tmp_path, "m1")
    layout.create_initiative(tmp_path, "i1")
    layout.create_project(tmp_path, "p1")
    archived = layout.archived_initiative_path(tmp_path, "old-init")
    archived.write_text("# Old\n", encoding="utf-8")

    assert layout.resolve_entity_path(tmp_path, "goals/g1.md")[0] == "goal"
    assert layout.resolve_entity_path(tmp_path, "milestones/m1.md")[0] == "milestone"
    assert layout.resolve_entity_path(tmp_path, "initiatives/i1.md")[0] == "initiative"
    assert (
        layout.resolve_entity_path(tmp_path, "initiatives/old-init.archived.md")[0]
        == "archived-initiative"
    )
    assert layout.resolve_entity_path(tmp_path, "projects/p1")[0] == "project"
    assert layout.resolve_entity_path(tmp_path, "projects/p1/p1.md")[0] == "project"

    with pytest.raises(BellmanLayoutError, match="invalid entity path"):
        layout.resolve_entity_path(tmp_path, ".")
    with pytest.raises(BellmanLayoutError, match="invalid goal path"):
        layout.resolve_entity_path(tmp_path, "goals/foo")
    with pytest.raises(BellmanLayoutError, match="invalid goal path"):
        layout.resolve_entity_path(tmp_path, "goals/a/b.md")
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "goals/missing.md")
    with pytest.raises(BellmanLayoutError, match="invalid milestone path"):
        layout.resolve_entity_path(tmp_path, "milestones/x")
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "milestones/missing.md")
    with pytest.raises(BellmanLayoutError, match="invalid initiative path"):
        layout.resolve_entity_path(tmp_path, "initiatives/x")
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "initiatives/missing.md")
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "projects/missing")
    foo = tmp_path / "projects" / "foo"
    foo.mkdir()
    (foo / "bar.md").write_text("# Wrong\n", encoding="utf-8")
    with pytest.raises(BellmanLayoutError, match="invalid project path"):
        layout.resolve_entity_path(tmp_path, "projects/foo/bar.md")
    with pytest.raises(BellmanLayoutError, match="invalid project path"):
        layout.resolve_entity_path(tmp_path, "projects/a/b/c")
    layout.create_initiative(tmp_path, "archived-proj")
    layout.promote_initiative(tmp_path, "archived-proj")
    layout.demote_project(tmp_path, "archived-proj")
    with pytest.raises(BellmanLayoutError, match="archived project"):
        layout.resolve_entity_path(tmp_path, "projects/archived-proj.archived")
    with pytest.raises(BellmanLayoutError, match="must be under"):
        layout.resolve_entity_path(tmp_path, "other/foo.md")


def test_resolve_entity_path_outside_via_symlink(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    outside = tmp_path.parent / "outside-goal.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    link = tmp_path / "goals" / "linked.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported")
    with pytest.raises(BellmanLayoutError, match="outside roadmap"):
        layout.resolve_entity_path(tmp_path, "goals/linked.md")


def test_find_entity_and_by_kind_errors(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with pytest.raises(BellmanLayoutError, match="no entity named"):
        layout.find_entity(tmp_path, "missing-entity")
    with pytest.raises(BellmanLayoutError, match="unknown entity kind"):
        layout.find_entity_by_kind(tmp_path, "bogus", "x")
    with pytest.raises(BellmanLayoutError, match="no project"):
        layout.find_entity_by_kind(tmp_path, "project", "missing")
    with pytest.raises(BellmanLayoutError, match="no initiative"):
        layout.find_entity_by_kind(tmp_path, "initiative", "missing")
    with pytest.raises(BellmanLayoutError, match="no milestone"):
        layout.find_entity_by_kind(tmp_path, "milestone", "missing")
    with pytest.raises(BellmanLayoutError, match="no goal"):
        layout.find_entity_by_kind(tmp_path, "goal", "missing")

    layout.create_initiative(tmp_path, "i-ok")
    layout.create_milestone(tmp_path, "m-ok")
    assert layout.find_entity_by_kind(tmp_path, "initiative", "i-ok")[0] == "initiative"
    assert layout.find_entity_by_kind(tmp_path, "milestone", "m-ok")[0] == "milestone"


def test_rename_same_name_and_archived(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "same-goal")
    with pytest.raises(BellmanLayoutError, match="already named"):
        layout.rename_entity(tmp_path, "same-goal", "same-goal")

    archived = layout.archived_initiative_path(tmp_path, "arch-old")
    archived.write_text("# Arch Old\n", encoding="utf-8")
    renamed = layout.rename_entity(
        tmp_path, "initiatives/arch-old.archived.md", "arch-new"
    )
    assert renamed.kind == "archived-initiative"
    assert layout.archived_initiative_path(tmp_path, "arch-new").is_file()


def test_rename_goal_without_heading(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    path = layout.goal_path(tmp_path, "plain-goal")
    path.write_text("No heading here.\n", encoding="utf-8")
    layout.rename_entity(tmp_path, "plain-goal", "plain-goal-2")
    text = layout.goal_path(tmp_path, "plain-goal-2").read_text(encoding="utf-8")
    assert "No heading here." in text


def test_rename_skips_unrelated_deps_and_loose_files(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "target-g")
    layout.create_initiative(tmp_path, "follower")
    initiative = layout.initiative_path(tmp_path, "follower")
    initiative.write_text(
        initiative.read_text(encoding="utf-8") + "- other-dep [FS, Mandatory]\n",
        encoding="utf-8",
    )
    projects = tmp_path / "projects"
    (projects / "loose.txt").write_text("x\n", encoding="utf-8")
    bare = projects / "bare-dir"
    bare.mkdir()
    layout.rename_entity(tmp_path, "target-g", "target-g2")
    text = initiative.read_text(encoding="utf-8")
    assert "- other-dep [FS, Mandatory]" in text


def test_rename_project_without_md(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    pdir = layout.project_dir(tmp_path, "no-md")
    pdir.mkdir()
    (pdir / "work-packages.yaml").write_text(
        "version: 1\nwork_packages: []\n", encoding="utf-8"
    )
    renamed = layout.rename_entity(tmp_path, "no-md", "no-md-2", kind="project")
    assert renamed.kind == "project"
    assert layout.project_dir(tmp_path, "no-md-2").is_dir()
    assert not (layout.project_dir(tmp_path, "no-md-2") / "no-md.md").exists()


def test_rename_rewrites_dict_and_inline_wp_deps(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "old-p")
    layout.create_project(tmp_path, "consumer")
    wp_path = layout.work_packages_path(tmp_path, "consumer")
    wp_path.write_text(
        """version: 1

work_packages:
  - title: A
    dependencies:
      - old-p/wp-a [FS, Mandatory]
      - old-p/wp-b [FS, Discretionary]
      -
        predecessor: old-p/wp-c
""",
        encoding="utf-8",
    )
    layout.rename_entity(tmp_path, "old-p", "new-p", kind="project")
    text = wp_path.read_text(encoding="utf-8")
    assert "new-p/wp-a" in text
    assert "new-p/wp-b" in text
    assert "new-p/wp-c" in text
    assert "old-p/" not in text


def test_promote_errors_and_existing_criteria(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    with pytest.raises(BellmanLayoutError, match="initiative not found"):
        layout.promote_initiative(tmp_path, "missing")
    layout.create_initiative(tmp_path, "clash")
    layout.create_project(tmp_path, "clash")
    with pytest.raises(BellmanLayoutError, match="project already exists"):
        layout.promote_initiative(tmp_path, "clash")

    layout.create_initiative(tmp_path, "has-criteria")
    path = layout.initiative_path(tmp_path, "has-criteria")
    path.write_text(
        path.read_text(encoding="utf-8") + "\n### Criteria for Success\n\nDone.\n",
        encoding="utf-8",
    )
    layout.promote_initiative(tmp_path, "has-criteria")
    md = layout.project_md_path(tmp_path, "has-criteria").read_text(encoding="utf-8")
    assert md.count("### Criteria for Success") == 1
    assert "Done." in md
