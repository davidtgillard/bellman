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
                            "id": "old-init",
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
                    "old_id": "a",
                    "new_id": "b",
                }
            ],
            "instances": [
                {
                    "guid": "770e8400-e29b-41d4-a716-446655440002",
                    "id": "live",
                    "type": "initiative",
                    "kind": "node",
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
        old_id="a",
        new_id="b",
        git_commit=None,
    )
    assert len(history.tombstones) == 1
    assert history.tombstones[0].instance_id == "old-init"
    assert history.tombstones[0].git_commit == "a" * 40
    assert len(history.instances) == 1
    assert history.instances[0].instance_id == "live"


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
