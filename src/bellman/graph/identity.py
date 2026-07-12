"""Map Bellman logical instance names to libfits wire GUIDs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyfits import Id
from pyfits.result import Err, Ok, Result

from bellman.graph.history import (
    BellmanHistoryError,
    GraphHistory,
    InstanceRecord,
    load_graph_history,
)
from bellman.graph.registry import KIND_TYPE

__all__ = ["InstanceIndex"]


def _qualified_path(
    inst: InstanceRecord,
    by_guid: dict[str, InstanceRecord],
) -> str:
    """Build ``parent/.../name`` from registry parent links."""
    segments: list[str] = [inst.instance_name]
    parent_guid = inst.parent_guid
    seen: set[str] = {inst.guid}
    while parent_guid is not None:
        if parent_guid in seen:
            break
        seen.add(parent_guid)
        parent = by_guid.get(parent_guid)
        if parent is None:
            break
        segments.append(parent.instance_name)
        parent_guid = parent.parent_guid
    segments.reverse()
    return "/".join(segments)


def _wire_guid(inst: InstanceRecord, by_guid: dict[str, InstanceRecord]) -> str:
    """Return child GUID or ``parent_guid/child`` wire path for nested nodes."""
    if inst.parent_guid is None:
        return inst.guid
    segments: list[str] = [inst.guid]
    parent_guid: str | None = inst.parent_guid
    seen: set[str] = {inst.guid}
    while parent_guid is not None:
        if parent_guid in seen:
            break
        seen.add(parent_guid)
        segments.append(parent_guid)
        parent = by_guid.get(parent_guid)
        if parent is None:
            break
        parent_guid = parent.parent_guid
    segments.reverse()
    return "/".join(segments)


@dataclass(frozen=True, slots=True)
class InstanceIndex:
    """Registry-backed lookup from logical instance names to wire GUIDs.

    Node keys are qualified name paths (``goal/reduce-churn``). Link keys remain
    the registry local ``name``.

    Attributes:
        by_name: Live instances keyed by logical qualified path (nodes) or
            local name (links).
        by_guid: Live instances keyed by child GUID and wire GUID path.
    """

    by_name: dict[str, InstanceRecord]
    by_guid: dict[str, InstanceRecord]

    @classmethod
    def from_history(cls, history: GraphHistory) -> InstanceIndex:
        """Build an index from a parsed registry snapshot."""
        by_child_guid: dict[str, InstanceRecord] = {
            inst.guid: inst for inst in history.instances if inst.kind == "node"
        }
        by_name: dict[str, InstanceRecord] = {}
        by_guid: dict[str, InstanceRecord] = {}
        for inst in history.instances:
            if inst.kind == "node":
                logical = _qualified_path(inst, by_child_guid)
            else:
                logical = inst.instance_name
            by_name[logical] = inst
            by_guid[inst.guid] = inst
            if inst.kind == "node":
                wire = _wire_guid(inst, by_child_guid)
                by_guid[wire] = inst
        return cls(by_name=by_name, by_guid=by_guid)

    @classmethod
    def load(cls, root: Path) -> Result[InstanceIndex, BellmanHistoryError]:
        """Load the registry at ``root`` and build an index.

        Args:
            root: Roadmap root directory.

        Returns:
            ``Ok(InstanceIndex)`` on success, or ``Err(BellmanHistoryError)``.
        """
        history_result = load_graph_history(root)
        if isinstance(history_result, Err):
            return history_result
        return Ok(cls.from_history(history_result.ok_value))

    def guid_for_name(self, name: str) -> Id | None:
        """Return the wire id for a logical instance name, if registered."""
        record = self.by_name.get(name)
        if record is None:
            return None
        children: dict[str, InstanceRecord] = {}
        for inst in self.by_guid.values():
            children[inst.guid] = inst
        return Id(_wire_guid(record, children))

    def name_for_guid(self, guid: str) -> str | None:
        """Return the logical instance name for a wire guid, if known."""
        record = self.by_guid.get(guid)
        if record is None:
            # Last path segment may be the child GUID.
            if "/" in guid:
                record = self.by_guid.get(guid.rsplit("/", 1)[-1])
            if record is None:
                return None
        if record.kind != "node":
            return record.instance_name
        children: dict[str, InstanceRecord] = {}
        for inst in self.by_guid.values():
            children[inst.guid] = inst
        return _qualified_path(record, children)

    def live_node_names(self) -> set[str]:
        """Return logical qualified names of live node instances (excl. kind)."""
        return {
            name
            for name, inst in self.by_name.items()
            if inst.kind == "node" and inst.type_name != KIND_TYPE
        }

    def live_kind_names(self) -> set[str]:
        """Return logical names of kind-root instances."""
        return {
            name
            for name, inst in self.by_name.items()
            if inst.kind == "node" and inst.type_name == KIND_TYPE
        }

    def guids_for_names(self, names: set[str]) -> set[str]:
        """Resolve logical node names to child wire guids, skipping unknown names."""
        out: set[str] = set()
        for name in names:
            record = self.by_name.get(name)
            if record is not None:
                out.add(record.guid)
        return out

    def children_of(self, parent_logical: str) -> list[InstanceRecord]:
        """Return live node instances whose parent path is ``parent_logical``."""
        parent = self.by_name.get(parent_logical)
        if parent is None or parent.kind != "node":
            return []
        return [
            inst
            for name, inst in self.by_name.items()
            if (
                inst.kind == "node"
                and inst.parent_guid == parent.guid
                and name.startswith(f"{parent_logical}/")
            )
        ]
