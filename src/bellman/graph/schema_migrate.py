"""Migrate registry schema and instance ids to kind-root nesting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

from bellman.graph.registry import KIND_ROOT_NAMES, KIND_TYPE

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


def registry_needs_schema_migration(root: Path) -> bool:
    """Return True when entity types are still root-scoped (no kind nesting).

    Fresh registries with no bellman entity types are left for
    :func:`bootstrap_registry` to create correctly via libfits.
    """
    path = root / _REGISTRY_PATH
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    node_types = data.get("node_types")
    if not isinstance(node_types, list):
        return False
    has_kind = False
    has_legacy_goal = False
    for entry in node_types:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == KIND_TYPE:
            has_kind = True
        if entry.get("type") == "goal":
            if entry.get("container_node") == KIND_TYPE:
                return False
            has_legacy_goal = True
    return has_legacy_goal and not has_kind


def migrate_registry_schema(root: Path) -> Result[None, FitsError]:
    """Strip legacy root-scoped bellman types so bootstrap can re-register nested ones.

    Markdown remains the source of truth: sync recreates nested nodes after
    :func:`bootstrap_registry` re-registers types via libfits (including
    ``create_folder``). Existing GUIDs for migrated entity/WP nodes are discarded.

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
    return Ok(None)


def is_kind_root_name(logical_name: str) -> bool:
    """Return True when ``logical_name`` is a kind-root path segment."""
    return logical_name in KIND_ROOT_NAMES
