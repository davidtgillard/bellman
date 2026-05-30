"""Integration tests for graph sync after roadmap mutations."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyfits.result import Err, Ok

from snark import layout
from snark.graph.history import load_graph_history
from snark.graph.sync import libfits_available, sync_roadmap


def _instance_type(root: Path, instance_id: str) -> str | None:
    result = load_graph_history(root)
    if isinstance(result, Err):
        return None
    for inst in result.ok_value.instances:
        if inst.instance_id == instance_id:
            return inst.type_name
    return None


def _has_live_instance(root: Path, instance_id: str) -> bool:
    return _instance_type(root, instance_id) is not None


@pytest.mark.integration
def test_create_initiative_registers_in_graph(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "settings-manager")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _instance_type(tmp_path, "settings-manager") == "initiative"
    assert _has_live_instance(tmp_path, "settings-manager")


@pytest.mark.integration
def test_delete_prunes_graph_node(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "my-goal")
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _has_live_instance(tmp_path, "my-goal")
    layout.delete_entity(tmp_path, "my-goal")
    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)
    assert not _has_live_instance(tmp_path, "my-goal")
    history = load_graph_history(tmp_path)
    assert isinstance(history, Ok)
    assert all(i.instance_id != "my-goal" for i in history.ok_value.instances)


@pytest.mark.integration
def test_promote_registers_project(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "grow-feature")
    assert isinstance(sync_roadmap(tmp_path), Ok)
    assert _instance_type(tmp_path, "grow-feature") == "initiative"
    layout.promote_initiative(tmp_path, "grow-feature")
    result = sync_roadmap(tmp_path)
    assert isinstance(result, Ok)
    assert _instance_type(tmp_path, "grow-feature") == "project"
    assert _has_live_instance(tmp_path, "grow-feature")
