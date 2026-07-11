"""Tests for InstanceIndex name↔guid resolution."""

from __future__ import annotations

from pyfits import Id

from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex


def test_instance_index_resolves_name_and_guid() -> None:
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="550e8400-e29b-41d4-a716-446655440000",
                instance_name="goal--reduce-churn",
                type_name="goal",
                kind="node",
            ),
            InstanceRecord(
                guid="660e8400-e29b-41d4-a716-446655440001",
                instance_name="parent_of--a--b",
                type_name="parent_of",
                kind="link",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    assert index.guid_for_name("goal--reduce-churn") == Id(
        "550e8400-e29b-41d4-a716-446655440000"
    )
    assert index.name_for_guid("550e8400-e29b-41d4-a716-446655440000") == (
        "goal--reduce-churn"
    )
    assert index.live_node_names() == {"goal--reduce-churn"}
    assert index.guids_for_names({"goal--reduce-churn"}) == {
        "550e8400-e29b-41d4-a716-446655440000"
    }
