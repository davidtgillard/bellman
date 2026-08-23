"""Tests for InstanceIndex name↔guid resolution."""

from __future__ import annotations

from pathlib import Path

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


def test_instance_index_cycle_and_missing_parent() -> None:
    a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=a,
                instance_name="a",
                type_name="goal",
                kind="node",
                parent_guid=b,
            ),
            InstanceRecord(
                guid=b,
                instance_name="b",
                type_name="goal",
                kind="node",
                parent_guid=a,
            ),
            InstanceRecord(
                guid="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                instance_name="orphan",
                type_name="goal",
                kind="node",
                parent_guid="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    # cycle breaks without infinite loop
    assert (
        index.guid_for_name("a/b") is not None or index.guid_for_name("b/a") is not None
    )
    assert index.name_for_guid("unknown") is None
    assert index.name_for_guid("parent_of--x--y") is None
    assert index.children_of("missing") == []
    assert index.guids_for_names({"missing", "orphan"}) == {
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    }


def test_instance_index_load_missing(tmp_path: Path) -> None:
    from pyfits.result import Err

    result = InstanceIndex.load(tmp_path)
    assert isinstance(result, Err)


def test_instance_index_link_name_for_guid() -> None:
    link_guid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=link_guid,
                instance_name="parent_of--a--b",
                type_name="parent_of",
                kind="link",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    assert index.name_for_guid(link_guid) == "parent_of--a--b"


def test_instance_index_children_of() -> None:
    kind_guid = "550e8400-e29b-41d4-a716-446655440000"
    child_guid = "660e8400-e29b-41d4-a716-446655440001"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=kind_guid,
                instance_name="goal",
                type_name="kind",
                kind="node",
            ),
            InstanceRecord(
                guid=child_guid,
                instance_name="child",
                type_name="goal",
                kind="node",
                parent_guid=kind_guid,
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    kids = index.children_of("goal")
    assert len(kids) == 1
    assert kids[0].instance_name == "child"


def test_name_for_guid_falls_back_to_child_segment() -> None:
    kind_guid = "550e8400-e29b-41d4-a716-446655440000"
    goal_guid = "660e8400-e29b-41d4-a716-446655440001"
    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid=kind_guid,
                instance_name="goal",
                type_name="kind",
                kind="node",
            ),
            InstanceRecord(
                guid=goal_guid,
                instance_name="reduce-churn",
                type_name="goal",
                kind="node",
                parent_guid=kind_guid,
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    # Wire path not stored under unknown parent prefix — last segment lookup
    assert index.name_for_guid(f"deadbeef/{goal_guid}") == "goal/reduce-churn"
