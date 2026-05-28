"""Layout and CLI filesystem tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from snark import layout
from snark.errors import SnarkLayoutError


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
    with pytest.raises(SnarkLayoutError, match="cannot be created"):
        layout.create_project(tmp_path, "foo.md")
