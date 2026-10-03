"""Migrate registry schema and instance ids to kind-root nesting."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

from bellman.graph.registry import KIND_ROOT_NAMES, KIND_TYPE, WORK_SCOPE_KIND_ROOT

_SCOPE_ENTITY_TYPES = frozenset({"initiative", "project"})

_REGISTRY_PATH = Path(".fits") / "registry.json"

_LEGACY_BELLMAN_TYPES = frozenset(
    {
        "initiative",
        "project",
        "work_package",
        "milestone",
        "goal",
        "work_scope",
        KIND_TYPE,
    }
)

_EXACT_MANAGED_LINKS = frozenset(
    {
        "parent_of",
        "promoted_from",
        "supports",
        "supports_wp",
        "targets",
        "targets_wp",
    }
)


def _is_managed_link_type(link_type: str) -> bool:
    return link_type in _EXACT_MANAGED_LINKS or link_type.startswith("precedes_")


def _load_registry(root: Path) -> dict[str, Any] | None:
    path = root / _REGISTRY_PATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _needs_legacy_root_scope_migration(data: dict[str, Any]) -> bool:
    """Return True when entity types are still root-scoped (no kind nesting)."""
    node_types = data.get("node_types")
    if not isinstance(node_types, list):
        return False
    has_kind = False
    has_legacy_milestone = False
    for entry in node_types:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == KIND_TYPE:
            has_kind = True
        if entry.get("type") == "milestone":
            if entry.get("container_node") == KIND_TYPE:
                return False
            has_legacy_milestone = True
    return has_legacy_milestone and not has_kind


def registry_needs_work_scope_parent_migration(root: Path) -> bool:
    """Return True when initiatives or projects are not under ``work_scope``.

    Nested libfits links can only connect siblings. Mixed project↔initiative
    precedence requires both types to share that kind-root parent.

    Args:
        root: Roadmap root directory.

    Returns:
        True when a live initiative or project instance is missing, or not
        parented to, the ``work_scope`` kind-root.
    """
    data = _load_registry(root)
    if data is None:
        return False
    return _needs_work_scope_parent_migration(data)


def _needs_work_scope_parent_migration(data: dict[str, Any]) -> bool:
    instances = data.get("instances")
    if not isinstance(instances, list):
        return False
    by_guid: dict[str, dict[str, Any]] = {}
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        guid = inst.get("guid")
        if isinstance(guid, str):
            by_guid[guid] = inst
    work_scope_guid: str | None = None
    for inst in by_guid.values():
        if (
            inst.get("kind") == "node"
            and inst.get("type") == KIND_TYPE
            and inst.get("name") == WORK_SCOPE_KIND_ROOT
        ):
            guid = inst.get("guid")
            if isinstance(guid, str):
                work_scope_guid = guid
                break
    for inst in by_guid.values():
        if inst.get("kind") != "node":
            continue
        if inst.get("type") not in _SCOPE_ENTITY_TYPES:
            continue
        parent = inst.get("parent_guid")
        if not isinstance(parent, str) or parent != work_scope_guid:
            return True
    return False


def registry_needs_schema_migration(root: Path) -> bool:
    """Return True when the registry layout is older than the current schema.

    Covers pre-kind-nesting types and work scopes not yet hosted under
    ``work_scope``. Fresh registries with no bellman entity types are left for
    :func:`bootstrap_registry` to create correctly via libfits.

    Args:
        root: Roadmap root directory.

    Returns:
        True when bootstrap should wipe and re-register bellman types.
    """
    data = _load_registry(root)
    if data is None:
        return False
    return _needs_legacy_root_scope_migration(
        data
    ) or _needs_work_scope_parent_migration(data)


def migrate_registry_schema(root: Path) -> Result[None, FitsError]:
    """Strip outdated bellman types so bootstrap can re-register the current schema.

    Markdown remains the source of truth: sync recreates nested nodes after
    :func:`bootstrap_registry` re-registers types via libfits (including
    ``create_folder``). Existing GUIDs for migrated entity/WP nodes are discarded.
    Nested ``nodes/`` payloads are removed so stale subgraph indexes cannot
    fail validation after instances are rewritten.

    Args:
        root: Roadmap root directory.

    Returns:
        ``Ok(None)`` when the registry already matches or was rewritten.
        ``Err(FitsError)`` when the registry cannot be read or written.
    """
    path = root / _REGISTRY_PATH
    if not path.is_file():
        return Ok(None)
    if not registry_needs_schema_migration(root):
        return Ok(None)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Err(FitsError(str(exc), code="schema_migration_failed"))

    old_types = data.get("node_types", [])
    kept_types: list[Any] = []
    if isinstance(old_types, list):
        for entry in old_types:
            if not isinstance(entry, dict):
                continue
            type_name = entry.get("type")
            if isinstance(type_name, str) and type_name in _LEGACY_BELLMAN_TYPES:
                continue
            kept_types.append(entry)
    data["node_types"] = kept_types

    old_instances = data.get("instances", [])
    kept_instances: list[Any] = []
    if isinstance(old_instances, list):
        for inst in old_instances:
            if not isinstance(inst, dict):
                continue
            type_name = inst.get("type")
            kind = inst.get("kind")
            if kind == "link":
                continue
            if isinstance(type_name, str) and type_name in _LEGACY_BELLMAN_TYPES:
                continue
            kept_instances.append(inst)
    data["instances"] = kept_instances

    old_links = data.get("link_types", [])
    kept_links: list[Any] = []
    if isinstance(old_links, list):
        for entry in old_links:
            if not isinstance(entry, dict):
                continue
            lt = entry.get("link_type")
            if isinstance(lt, str) and _is_managed_link_type(lt):
                continue
            kept_links.append(entry)
    data["link_types"] = kept_links
    data["nested_link_types"] = []
    if isinstance(data.get("nested_scopes"), dict):
        data["nested_scopes"] = {}

    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return Err(FitsError(str(exc), code="schema_migration_failed"))

    links_path = root / "links" / "links.jsonc"
    if links_path.is_file():
        try:
            links_path.write_text(
                "{\n"
                '  "description": "Directed links between issued object ids. '
                'Edit by hand or via fits CLI; validate with fits validate.",\n'
                '  "version": 1,\n'
                '  "kind": "fits-links-v1",\n'
                '  "links": []\n'
                "}\n",
                encoding="utf-8",
            )
        except OSError as exc:
            return Err(FitsError(str(exc), code="schema_migration_failed"))
    nodes_dir = root / "nodes"
    if nodes_dir.is_dir():
        try:
            shutil.rmtree(nodes_dir)
        except OSError as exc:
            return Err(FitsError(str(exc), code="schema_migration_failed"))
    return Ok(None)


def is_kind_root_name(logical_name: str) -> bool:
    """Return True when ``logical_name`` is a kind-root path segment."""
    return logical_name in KIND_ROOT_NAMES


_OBSOLETE_LINK_TYPES = frozenset({"promoted_from", "supports", "supports_wp"})
_OBSOLETE_NODE_TYPES = frozenset({"goal"})
_OBSOLETE_KIND_ROOT_NAMES = frozenset({"goal"})


def _is_obsolete_node_instance(inst: dict[str, Any]) -> bool:
    """Return True when ``inst`` is a retired goal node or goal kind-root."""
    if inst.get("kind") != "node":
        return False
    type_name = inst.get("type")
    if type_name in _OBSOLETE_NODE_TYPES:
        return True
    return type_name == KIND_TYPE and inst.get("name") in _OBSOLETE_KIND_ROOT_NAMES


def _drop_obsolete_goal_subgraphs(
    root: Path, kind_root_guids: set[str]
) -> Result[set[str], FitsError]:
    """Delete goal kind-root subgraphs and strip retired links from the rest.

    Args:
        root: Roadmap root directory.
        kind_root_guids: Child GUIDs of removed ``goal`` kind-root instances.

    Returns:
        ``Ok(guids)`` of retired links removed from surviving subgraph files.
        ``Err(FitsError)`` when a retired subgraph directory cannot be removed.
    """
    removed: set[str] = set()
    nodes_dir = root / "nodes"
    if not nodes_dir.is_dir():
        return Ok(removed)
    obsolete_dirs: list[Path] = []
    for sub_path in nodes_dir.rglob("subgraph.jsonc"):
        try:
            document = json.loads(sub_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        container = sub_path.parent.parent
        parent = document.get("parent_guid")
        if container.name == "goal goal" or (
            isinstance(parent, str) and parent in kind_root_guids
        ):
            obsolete_dirs.append(container)
            continue
        links = document.get("links")
        if not isinstance(links, list):
            continue
        kept: list[Any] = []
        changed_links = False
        for link in links:
            if isinstance(link, dict) and link.get("link_type") in _OBSOLETE_LINK_TYPES:
                guid = link.get("guid")
                if isinstance(guid, str):
                    removed.add(guid)
                changed_links = True
                continue
            kept.append(link)
        if not changed_links:
            continue
        document["links"] = kept
        try:
            sub_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        except OSError:
            continue
    for directory in obsolete_dirs:
        if not directory.is_dir():
            continue
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            return Err(FitsError(str(exc), code="schema_migration_failed"))
    return Ok(removed)


def remove_obsolete_link_types(root: Path) -> Result[set[str], FitsError]:
    """Drop retired link and goal types from the registry file.

    Removes ``promoted_from``, ``supports``, and ``supports_wp`` link types and
    instances, plus the ``goal`` node type, live goal nodes, and the ``goal``
    kind-root. Call before opening a long-lived repo session; pass returned
    GUIDs to ``reconcile_link_artifacts`` so subgraph and ``links.jsonc`` rows
    are dropped.

    Args:
        root: Roadmap root directory.

    Returns:
        ``Ok(guids)`` with child GUIDs of removed link instances (possibly empty).
        ``Err(FitsError)`` when the registry cannot be read or written, or a
        retired goal subgraph directory cannot be removed.
    """
    path = root / _REGISTRY_PATH
    stale_guids: set[str] = set()
    kind_root_guids: set[str] = set()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return Err(FitsError(str(exc), code="schema_migration_failed"))
        if isinstance(data, dict):
            changed = False
            instances = data.get("instances")
            if isinstance(instances, list):
                kept_instances: list[Any] = []
                for inst in instances:
                    if not isinstance(inst, dict):
                        kept_instances.append(inst)
                        continue
                    type_name = inst.get("type")
                    guid = inst.get("guid")
                    if _is_obsolete_node_instance(inst):
                        if type_name == KIND_TYPE and isinstance(guid, str):
                            kind_root_guids.add(guid)
                        changed = True
                        continue
                    if (
                        inst.get("kind") == "link"
                        and type_name in _OBSOLETE_LINK_TYPES
                        and isinstance(guid, str)
                    ):
                        stale_guids.add(guid)
                        continue
                    kept_instances.append(inst)
                if len(kept_instances) != len(instances):
                    data["instances"] = kept_instances
                    changed = True

            node_types = data.get("node_types")
            if isinstance(node_types, list):
                filtered_types = [
                    entry
                    for entry in node_types
                    if not (
                        isinstance(entry, dict)
                        and entry.get("type") in _OBSOLETE_NODE_TYPES
                    )
                ]
                if len(filtered_types) != len(node_types):
                    data["node_types"] = filtered_types
                    changed = True

            nested = data.get("nested_link_types")
            if isinstance(nested, list):
                filtered = [
                    entry
                    for entry in nested
                    if not (
                        isinstance(entry, dict)
                        and entry.get("link_type") in _OBSOLETE_LINK_TYPES
                    )
                ]
                if len(filtered) != len(nested):
                    data["nested_link_types"] = filtered
                    changed = True

            root_links = data.get("link_types")
            if isinstance(root_links, list):
                filtered_root = [
                    entry
                    for entry in root_links
                    if not (
                        isinstance(entry, dict)
                        and entry.get("link_type") in _OBSOLETE_LINK_TYPES
                    )
                ]
                if len(filtered_root) != len(root_links):
                    data["link_types"] = filtered_root
                    changed = True

            if changed:
                try:
                    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                except OSError as exc:
                    return Err(FitsError(str(exc), code="schema_migration_failed"))

    dropped = _drop_obsolete_goal_subgraphs(root, kind_root_guids)
    if isinstance(dropped, Err):
        return dropped
    stale_guids |= dropped.ok_value
    return Ok(stale_guids)
