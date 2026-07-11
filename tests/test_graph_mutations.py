"""Integration tests for graph sync after roadmap mutations."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyfits.result import Err, Ok

from bellman import layout
from bellman.graph.history import load_graph_history
from bellman.graph.sync import (
    init_pyfits_repo,
    libfits_available,
    prune_deleted_entity,
    sync_roadmap,
)


def _instance_type(root: Path, instance_name: str) -> str | None:
    result = load_graph_history(root)
    if isinstance(result, Err):
        return None
    for inst in result.ok_value.instances:
        if inst.instance_name == instance_name:
            return inst.type_name
    return None


def _has_live_instance(root: Path, instance_name: str) -> bool:
    return _instance_type(root, instance_name) is not None


def _bootstrap_pyfits(root: Path) -> None:
    result = init_pyfits_repo(root)
    assert isinstance(result, Ok)


@pytest.mark.integration
def test_create_initiative_registers_in_graph(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_initiative(tmp_path, "settings-manager")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _instance_type(tmp_path, "initiative--settings-manager") == "initiative"
    assert _has_live_instance(tmp_path, "initiative--settings-manager")


@pytest.mark.integration
def test_delete_prunes_graph_node(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_goal(tmp_path, "my-goal")
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _has_live_instance(tmp_path, "goal--my-goal")
    layout.delete_entity(tmp_path, "my-goal")
    result = prune_deleted_entity(tmp_path, "goal", "my-goal")
    assert isinstance(result, Ok)
    assert not _has_live_instance(tmp_path, "goal--my-goal")
    history = load_graph_history(tmp_path)
    assert isinstance(history, Ok)
    assert all(i.instance_name != "goal--my-goal" for i in history.ok_value.instances)


@pytest.mark.integration
def test_promote_registers_project(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_initiative(tmp_path, "grow-feature")
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _instance_type(tmp_path, "initiative--grow-feature") == "initiative"
    layout.promote_initiative(tmp_path, "grow-feature")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _instance_type(tmp_path, "project--grow-feature") == "project"
    assert _has_live_instance(tmp_path, "project--grow-feature")
    assert not _has_live_instance(tmp_path, "initiative--grow-feature")


@pytest.mark.integration
def test_sync_coexists_goal_and_initiative_same_name(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    _bootstrap_pyfits(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _has_live_instance(tmp_path, "goal--system-mci")
    assert _has_live_instance(tmp_path, "initiative--system-mci")
