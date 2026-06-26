"""Detect pre-migration flat node ids in pyfits registries."""

from __future__ import annotations

import re

from bellman.graph.desired import DesiredNode
from bellman.graph.registry import bellman_node_types

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_QUALIFIED_PREFIXES = ("initiative--", "project--", "goal--", "milestone--")


def is_legacy_flat_node_id(type_name: str, instance_id: str) -> bool:
    """Return True when ``instance_id`` uses the pre-migration bare kebab scheme.

    Args:
        type_name: Bellman node type from the registry (e.g. ``goal``).
        instance_id: Opaque instance id stored in ``registry.json``.

    Returns:
        True for bare kebab ids on bellman node types; false for qualified ids
        and work-package ids (``project--slug``).
    """
    if type_name not in bellman_node_types():
        return False
    if type_name == "work_package":
        return False
    if instance_id.startswith(_QUALIFIED_PREFIXES):
        return False
    return _KEBAB_RE.match(instance_id) is not None


def registry_needs_id_migration(
    actual_nodes: set[DesiredNode],
    desired_nodes: set[DesiredNode],
) -> bool:
    """Return True when the registry likely uses legacy flat node ids.

    Args:
        actual_nodes: Live registry node instances.
        desired_nodes: Nodes implied by the loaded markdown roadmap.

    Returns:
        True when actual nodes include legacy flat ids and desired nodes use
        type-qualified ids.
    """
    if not actual_nodes or not desired_nodes:
        return False
    has_legacy = any(
        is_legacy_flat_node_id(node.type_name, node.node_id) for node in actual_nodes
    )
    has_qualified = any(
        node.node_id.startswith(_QUALIFIED_PREFIXES) for node in desired_nodes
    )
    return has_legacy and has_qualified
