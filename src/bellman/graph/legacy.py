"""Detect pre-migration flat and ``--``-qualified node ids in pyfits registries."""

from __future__ import annotations

import re

from bellman.graph.desired import DesiredNode
from bellman.graph.registry import bellman_node_types

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_DASH_QUALIFIED_PREFIXES = ("initiative--", "project--", "goal--", "milestone--")
_SLASH_QUALIFIED_PREFIXES = ("initiative/", "project/", "goal/", "milestone/")


def is_legacy_flat_node_id(type_name: str, instance_name: str) -> bool:
    """Return True when ``instance_name`` uses the pre-migration bare kebab scheme.

    Args:
        type_name: Bellman node type from the registry (e.g. ``goal``).
        instance_name: Human instance name stored in ``registry.json``.

    Returns:
        True for bare kebab names on bellman node types; false for qualified
        names and work-package path names.
    """
    if type_name not in bellman_node_types():
        return False
    if type_name == "work_package":
        return False
    if instance_name.startswith(_DASH_QUALIFIED_PREFIXES):
        return False
    if instance_name.startswith(_SLASH_QUALIFIED_PREFIXES):
        return False
    if "/" in instance_name:
        return False
    return _KEBAB_RE.match(instance_name) is not None


def is_legacy_dash_qualified_id(node_id: str) -> bool:
    """Return True when ``node_id`` uses ``type--name`` or ``project--slug``."""
    if node_id.startswith(_DASH_QUALIFIED_PREFIXES):
        return True
    # work package: project--slug (no type prefix)
    if "--" in node_id and "/" not in node_id:
        left, _right = node_id.split("--", 1)
        return bool(_KEBAB_RE.match(left))
    return False


def registry_needs_id_migration(
    actual_nodes: set[DesiredNode],
    desired_nodes: set[DesiredNode],
) -> bool:
    """Return True when the registry likely uses legacy flat or ``--`` ids.

    Args:
        actual_nodes: Live registry node instances.
        desired_nodes: Nodes implied by the loaded markdown roadmap.

    Returns:
        True when actual nodes include legacy ids and desired nodes use
        slash-qualified paths.
    """
    if not actual_nodes or not desired_nodes:
        return False
    has_legacy = any(
        is_legacy_flat_node_id(node.type_name, node.node_id)
        or is_legacy_dash_qualified_id(node.node_id)
        for node in actual_nodes
    )
    has_slash = any(
        node.node_id.startswith(_SLASH_QUALIFIED_PREFIXES)
        or node.node_id.startswith("project/")
        for node in desired_nodes
    )
    return has_legacy and has_slash
