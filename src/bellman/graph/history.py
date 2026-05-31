"""Graph registry audit history from ``.fits/registry.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pyfits.result import Err, Ok, Result

__all__ = [
    "GraphHistory",
    "InstanceRecord",
    "InstanceRename",
    "BellmanHistoryError",
    "TombstoneRecord",
    "load_graph_history",
]

_REGISTRY_KIND = "fits-registry"
_REGISTRY_PATH = Path(".fits") / "registry.json"


@dataclass(frozen=True, slots=True)
class BellmanHistoryError:
    """Failure loading graph history from the roadmap repository."""

    message: str
    path: str | None = None

    def format(self) -> str:
        if self.path is not None:
            return f"{self.path}: {self.message}"
        return self.message


@dataclass(frozen=True, slots=True)
class InstanceRename:
    """Recorded rename of a graph instance (GUID stable)."""

    guid: str
    old_id: str
    new_id: str
    git_commit: str | None = None


@dataclass(frozen=True, slots=True)
class TombstoneRecord:
    """Removed or retired instance id for a registered type."""

    type_name: str
    kind: Literal["node", "link"]
    instance_id: str | None = None
    numeric_id: int | None = None
    guid: str | None = None
    git_commit: str | None = None


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    """Live instance row from the registry index."""

    guid: str
    instance_id: str
    type_name: str
    kind: Literal["node", "link"]
    scope: str = "root"
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class GraphHistory:
    """Registry audit snapshot: renames, tombstones, and live instances.

    v1 reflects libfits registry fields, not a full mutation event log.
    """

    renames: tuple[InstanceRename, ...] = ()
    tombstones: tuple[TombstoneRecord, ...] = ()
    instances: tuple[InstanceRecord, ...] = ()


def load_graph_history(root: Path) -> Result[GraphHistory, BellmanHistoryError]:
    """Load graph history from the roadmap pyfits registry.

    Uses ``.fits/registry.json`` under ``root``. When pyfits exposes a
    dedicated history operation, this function may delegate there first.

    Args:
        root: Roadmap root directory.

    Returns:
        ``Ok(GraphHistory)`` on success, or ``Err(BellmanHistoryError)`` when
        the registry is missing or invalid.
    """
    registry_path = root.resolve() / _REGISTRY_PATH
    if not registry_path.is_file():
        return Err(
            BellmanHistoryError(
                "graph registry not found; run `bellman init` or `bellman sync`",
                path=str(registry_path),
            )
        )
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Err(
            BellmanHistoryError(
                f"cannot read registry: {exc}",
                path=str(registry_path),
            )
        )
    if not isinstance(raw, dict):
        return Err(
            BellmanHistoryError(
                "registry root must be a JSON object",
                path=str(registry_path),
            )
        )
    kind = raw.get("kind")
    if kind != _REGISTRY_KIND:
        return Err(
            BellmanHistoryError(
                f'expected kind "{_REGISTRY_KIND}", got {kind!r}',
                path=str(registry_path),
            )
        )
    return Ok(_parse_registry(raw))


def _parse_registry(raw: dict[str, Any]) -> GraphHistory:
    renames = _parse_renames(raw.get("instance_renames"))
    tombstones: list[TombstoneRecord] = []
    for entry in raw.get("node_types") or []:
        if isinstance(entry, dict) and entry.get("type"):
            tombstones.extend(_parse_tombstones(entry, kind="node"))
    for entry in raw.get("link_types") or []:
        if isinstance(entry, dict) and entry.get("link_type"):
            tombstones.extend(_parse_tombstones(entry, kind="link"))
    for entry in raw.get("nested_link_types") or []:
        if isinstance(entry, dict) and entry.get("link_type"):
            tombstones.extend(_parse_tombstones(entry, kind="link"))
    instances = _parse_instances(raw.get("instances"))
    return GraphHistory(
        renames=tuple(renames),
        tombstones=tuple(tombstones),
        instances=tuple(instances),
    )


def _parse_renames(raw: Any) -> list[InstanceRename]:
    if not isinstance(raw, list):
        return []
    out: list[InstanceRename] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        guid = item.get("guid")
        old_id = item.get("old_id")
        new_id = item.get("new_id")
        if not (
            isinstance(guid, str)
            and isinstance(old_id, str)
            and isinstance(new_id, str)
        ):
            continue
        git_commit = item.get("git_commit")
        out.append(
            InstanceRename(
                guid=guid,
                old_id=old_id,
                new_id=new_id,
                git_commit=git_commit if isinstance(git_commit, str) else None,
            )
        )
    return out


def _parse_tombstones(
    type_entry: dict[str, Any],
    *,
    kind: Literal["node", "link"],
) -> list[TombstoneRecord]:
    type_name = (
        type_entry.get("type") if kind == "node" else type_entry.get("link_type")
    )
    if not isinstance(type_name, str):
        return []
    raw_ts = type_entry.get("tombstones")
    if not isinstance(raw_ts, list):
        return []
    out: list[TombstoneRecord] = []
    for ts in raw_ts:
        if not isinstance(ts, dict):
            continue
        guid = ts.get("guid")
        git_commit = ts.get("git_commit")
        if "n" in ts and isinstance(ts["n"], int):
            out.append(
                TombstoneRecord(
                    type_name=type_name,
                    kind=kind,
                    numeric_id=ts["n"],
                    guid=guid if isinstance(guid, str) else None,
                    git_commit=(git_commit if isinstance(git_commit, str) else None),
                )
            )
        elif "id" in ts and isinstance(ts["id"], str):
            out.append(
                TombstoneRecord(
                    type_name=type_name,
                    kind=kind,
                    instance_id=ts["id"],
                    guid=guid if isinstance(guid, str) else None,
                    git_commit=(git_commit if isinstance(git_commit, str) else None),
                )
            )
    return out


def _parse_instances(raw: Any) -> list[InstanceRecord]:
    if not isinstance(raw, list):
        return []
    out: list[InstanceRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        guid = item.get("guid")
        instance_id = item.get("id")
        type_name = item.get("type")
        item_kind = item.get("kind")
        if not (
            isinstance(guid, str)
            and isinstance(instance_id, str)
            and isinstance(type_name, str)
            and item_kind in ("node", "link")
        ):
            continue
        scope = item.get("scope")
        parent_id = item.get("parent_id")
        out.append(
            InstanceRecord(
                guid=guid,
                instance_id=instance_id,
                type_name=type_name,
                kind=item_kind,
                scope=scope if isinstance(scope, str) else "root",
                parent_id=parent_id if isinstance(parent_id, str) else None,
            )
        )
    return out
