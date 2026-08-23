"""Tests for graph registry history loading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pyfits.result import Err, Ok

from bellman.graph.history import (
    GraphHistory,
    InstanceRename,
    load_graph_history,
)
from bellman.plugin.context import BellmanContext


def _write_registry(root: Path, payload: dict) -> None:
    fits = root / ".fits"
    fits.mkdir(parents=True)
    (fits / "registry.json").write_text(json.dumps(payload), encoding="utf-8")


def test_load_graph_history_missing_registry(tmp_path: Path) -> None:
    result = load_graph_history(tmp_path)
    assert isinstance(result, Err)
    assert "not found" in result.err_value.message


def test_load_graph_history_renames_and_tombstones(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "description": "test",
            "version": 1,
            "kind": "fits-registry",
            "node_types": [
                {
                    "type": "initiative",
                    "extends": "work_scope",
                    "next": 2,
                    "tombstones": [
                        {
                            "name": "old-init",
                            "guid": "550e8400-e29b-41d4-a716-446655440000",
                            "git_commit": "a" * 40,
                        }
                    ],
                }
            ],
            "link_types": [],
            "instance_renames": [
                {
                    "guid": "660e8400-e29b-41d4-a716-446655440001",
                    "old_name": "a",
                    "new_name": "b",
                }
            ],
            "instances": [
                {
                    "guid": "770e8400-e29b-41d4-a716-446655440002",
                    "name": "live",
                    "type": "initiative",
                    "kind": "node",
                    "scope": "root",
                }
            ],
        },
    )
    result = load_graph_history(tmp_path)
    assert isinstance(result, Ok)
    history = result.ok_value
    assert len(history.renames) == 1
    assert history.renames[0] == InstanceRename(
        guid="660e8400-e29b-41d4-a716-446655440001",
        old_name="a",
        new_name="b",
        git_commit=None,
    )
    assert len(history.tombstones) == 1
    assert history.tombstones[0].instance_name == "old-init"
    assert history.tombstones[0].git_commit == "a" * 40
    assert len(history.instances) == 1
    assert history.instances[0].instance_name == "live"


def test_bellman_context_history_lazy_no_repo(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "description": "test",
            "version": 1,
            "kind": "fits-registry",
            "node_types": [],
            "link_types": [],
        },
    )
    ctx = BellmanContext(root=tmp_path)
    with patch("bellman.plugin.context.Repo.open") as open_mock:
        history = ctx.history()
        open_mock.assert_not_called()
    assert isinstance(history, GraphHistory)


def test_load_graph_history_invalid_json(tmp_path: Path) -> None:
    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text("{not json", encoding="utf-8")
    result = load_graph_history(tmp_path)
    assert isinstance(result, Err)
    assert "cannot read registry" in result.err_value.message


def test_load_graph_history_wrong_kind(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"kind": "other", "version": 1})
    result = load_graph_history(tmp_path)
    assert isinstance(result, Err)
    assert "expected kind" in result.err_value.message


def test_load_graph_history_not_object(tmp_path: Path) -> None:
    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text("[1, 2]", encoding="utf-8")
    result = load_graph_history(tmp_path)
    assert isinstance(result, Err)


def test_parse_numeric_tombstone_and_skips(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "description": "test",
            "version": 1,
            "kind": "fits-registry",
            "node_types": [
                {
                    "type": "goal",
                    "tombstones": [
                        {"n": 7, "guid": "g1"},
                        "skip-me",
                        {"name": "named", "git_commit": "c" * 40},
                    ],
                }
            ],
            "link_types": [
                {
                    "link_type": "parent_of",
                    "tombstones": [{"name": "old-link"}],
                }
            ],
            "nested_link_types": [
                {
                    "link_type": "contains",
                    "tombstones": [{"n": 3}],
                }
            ],
            "instance_renames": [
                "skip",
                {"guid": "g", "old_name": "a"},  # incomplete
                {
                    "guid": "g2",
                    "old_name": "old",
                    "new_name": "new",
                    "git_commit": "d" * 40,
                },
            ],
            "instances": [
                "skip",
                {
                    "guid": "i1",
                    "name": "live",
                    "type": "goal",
                    "kind": "node",
                    "scope": "nested",
                    "parent_guid": "p1",
                },
            ],
        },
    )
    result = load_graph_history(tmp_path)
    assert isinstance(result, Ok)
    history = result.ok_value
    assert any(t.numeric_id == 7 for t in history.tombstones)
    assert any(t.instance_name == "named" for t in history.tombstones)
    assert any(t.instance_name == "old-link" for t in history.tombstones)
    assert any(t.numeric_id == 3 for t in history.tombstones)
    assert len(history.renames) == 1
    assert history.renames[0].git_commit == "d" * 40
    assert history.instances[0].parent_guid == "p1"


def test_bellman_history_error_format() -> None:
    from bellman.graph.history import BellmanHistoryError

    assert BellmanHistoryError("m", path="p").format() == "p: m"
    assert BellmanHistoryError("m").format() == "m"
