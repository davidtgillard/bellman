"""Tests for links.jsonc reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyfits import Repo
from pyfits.result import Ok

from bellman import layout
from bellman.graph.links_file import reconcile_link_artifacts
from bellman.graph.sync import (
    init_pyfits_repo,
    libfits_available,
    prune_deleted_entity,
    sync_roadmap,
)

_NODE_GUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_MISSING_GUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
_LINK_GUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def test_reconcile_drops_unregistered_links(tmp_path: Path) -> None:
    registry_path = tmp_path / ".fits"
    registry_path.mkdir(parents=True)
    links_dir = tmp_path / "links"
    links_dir.mkdir()
    (registry_path / "registry.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "name": "a",
                        "kind": "node",
                        "type": "goal",
                        "guid": _NODE_GUID,
                        "scope": "root",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (links_dir / "links.jsonc").write_text(
        json.dumps(
            {
                "kind": "fits-links-v1",
                "version": 1,
                "links": [
                    {
                        "guid": _LINK_GUID,
                        "link_type": "parent_of",
                        "in": _NODE_GUID,
                        "out": _MISSING_GUID,
                        "labels": None,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = reconcile_link_artifacts(tmp_path)

    assert isinstance(result, Ok)
    assert result.ok_value == 1
    links = json.loads((links_dir / "links.jsonc").read_text(encoding="utf-8"))
    assert links["links"] == []


@pytest.mark.integration
def test_prune_deleted_initiative_with_scope_dependency(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "dep-init")
    layout.create_initiative(tmp_path, "target-init")
    dep_path = layout.initiative_path(tmp_path, "dep-init")
    dep_path.write_text(
        dep_path.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- target-init [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    assert isinstance(init_pyfits_repo(tmp_path), Ok)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    layout.delete_entity(tmp_path, "dep-init")
    result = prune_deleted_entity(tmp_path, "initiative", "dep-init")

    assert isinstance(result, Ok)
    open_result = Repo.open(tmp_path)
    assert isinstance(open_result, Ok)
    with open_result.ok_value as repo:
        assert isinstance(repo.validate(), Ok)
