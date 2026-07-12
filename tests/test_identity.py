"""Tests for InstanceIndex name↔guid resolution."""

from __future__ import annotations

from pyfits import Id

from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex


def test_instance_index_resolves_qualified_paths() -> None:
    kind_guid = "550e8400-e29b-41d4-a716-446655440000"
    goal_guid = "660e8400-e29b-41d4-a716-446655440001"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=kind_guid,
                instance_name="goal",
                type_name="kind",
                kind="node",
                scope="root",
            ),
            InstanceRecord(
                guid=goal_guid,
                instance_name="reduce-churn",
                type_name="goal",
                kind="node",
                scope="nested",
                parent_guid=kind_guid,
            ),
            InstanceRecord(
                guid="770e8400-e29b-41d4-a716-446655440002",
                instance_name="parent_of--a--b",
                type_name="parent_of",
                kind="link",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    assert index.guid_for_name("goal/reduce-churn") == Id(f"{kind_guid}/{goal_guid}")
    assert index.name_for_guid(goal_guid) == "goal/reduce-churn"
    assert index.name_for_guid(f"{kind_guid}/{goal_guid}") == "goal/reduce-churn"
    assert index.live_node_names() == {"goal/reduce-churn"}
    assert index.live_kind_names() == {"goal"}
    assert index.guids_for_names({"goal/reduce-churn"}) == {goal_guid}
