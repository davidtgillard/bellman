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

__all__ = ["InstanceIndex"]


@dataclass(frozen=True, slots=True)
class InstanceIndex:
    """Registry-backed lookup from logical instance names to wire GUIDs.

    Attributes:
        by_name: Live instances keyed by human ``name`` from ``registry.json``.
        by_guid: Live instances keyed by wire ``guid``.
    """

    by_name: dict[str, InstanceRecord]
    by_guid: dict[str, InstanceRecord]

    @classmethod
    def from_history(cls, history: GraphHistory) -> InstanceIndex:
        """Build an index from a parsed registry snapshot."""
        by_name: dict[str, InstanceRecord] = {}
        by_guid: dict[str, InstanceRecord] = {}
        for inst in history.instances:
            by_name[inst.instance_name] = inst
            by_guid[inst.guid] = inst
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
        return Id(record.guid)

    def name_for_guid(self, guid: str) -> str | None:
        """Return the logical instance name for a wire guid, if known."""
        record = self.by_guid.get(guid)
        if record is None:
            return None
        return record.instance_name

    def live_node_names(self) -> set[str]:
        """Return logical names of all live node instances."""
        return {
            inst.instance_name for inst in self.by_name.values() if inst.kind == "node"
        }

    def guids_for_names(self, names: set[str]) -> set[str]:
        """Resolve logical node names to wire guids, skipping unknown names."""
        out: set[str] = set()
        for name in names:
            record = self.by_name.get(name)
            if record is not None:
                out.add(record.guid)
        return out
