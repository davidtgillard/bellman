"""Integration tests for legacy flat-id migration during sync prune."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyfits import Repo
from pyfits.result import Ok

from bellman import layout
from bellman.graph.desired import entity_node_id
from bellman.graph.history import load_graph_history
from bellman.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap


def _write_registry_instances(root: Path, instances: list[dict[str, str]]) -> None:
    registry_path = root / ".fits" / "registry.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    data["instances"] = instances
    registry_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.mark.integration
def test_sync_prune_tolerates_legacy_registry_ghosts(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")

    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "manual-goal")
    assert isinstance(init_pyfits_repo(tmp_path), Ok)
    assert isinstance(sync_roadmap(tmp_path), Ok)

    qualified = entity_node_id("goal", "manual-goal")
    history = load_graph_history(tmp_path)
    assert isinstance(history, Ok)
    guid = history.ok_value.instances[0].guid
    _write_registry_instances(
        tmp_path,
        [
            {
                "guid": guid,
                "id": "manual-goal",
                "type": "goal",
                "kind": "node",
                "scope": "root",
            },
            {
                "guid": guid,
                "id": qualified,
                "type": "goal",
                "kind": "node",
                "scope": "root",
            },
        ],
    )

    result = sync_roadmap(tmp_path, prune=True)
    assert isinstance(result, Ok)

    open_result = Repo.open(tmp_path)
    assert isinstance(open_result, Ok)
    with open_result.ok_value as repo:
        graph = repo.output_graph()
        assert isinstance(graph, Ok)
        node_ids = {node.id.value for node in graph.ok_value.nodes}
        validation = repo.validate()
    assert qualified in node_ids
    assert isinstance(validation, Ok)
