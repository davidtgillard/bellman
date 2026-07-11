"""Repair ``links/links.jsonc`` against ``.fits/registry.json``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

from bellman.graph.identity import InstanceIndex

_REGISTRY_PATH = Path(".fits") / "registry.json"
_LINKS_PATH = Path("links") / "links.jsonc"
_JSONC_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)


def _load_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    cleaned = _JSONC_COMMENT_RE.sub("", text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        msg = f"links file must be a JSON object: {path}"
        raise ValueError(msg)
    return data


def _registered_guids(registry: dict[str, Any]) -> set[str]:
    instances = registry.get("instances", [])
    if not isinstance(instances, list):
        return set()
    return {
        inst["guid"]
        for inst in instances
        if isinstance(inst, dict) and isinstance(inst.get("guid"), str)
    }


def _registered_node_guids(registry: dict[str, Any]) -> set[str]:
    instances = registry.get("instances", [])
    if not isinstance(instances, list):
        return set()
    return {
        inst["guid"]
        for inst in instances
        if (
            isinstance(inst, dict)
            and inst.get("kind") == "node"
            and isinstance(inst.get("guid"), str)
        )
    }


def _link_is_valid(
    link: dict[str, Any],
    *,
    registered: set[str],
    node_guids: set[str],
    drop_touching_guids: set[str],
) -> bool:
    link_guid = link.get("guid")
    in_guid = link.get("in")
    out_guid = link.get("out")
    if not isinstance(link_guid, str):
        return False
    if not isinstance(in_guid, str) or not isinstance(out_guid, str):
        return False
    if link_guid not in registered:
        return False
    if in_guid not in node_guids or out_guid not in node_guids:
        return False
    if in_guid in drop_touching_guids or out_guid in drop_touching_guids:
        return False
    return True


def reconcile_link_artifacts(
    root: Path,
    *,
    drop_touching_nodes: set[str] | None = None,
) -> Result[int, FitsError]:
    """Drop invalid ``links.jsonc`` rows and stale link registry instances.

    Removes links when:
    - the link guid is not registered in ``instances[]``
    - either endpoint guid is not a registered node instance
    - either endpoint guid matches a node listed in ``drop_touching_nodes``

    Args:
        root: Roadmap root directory.
        drop_touching_nodes: Optional logical node names whose incident links
            should be removed.

    Returns:
        ``Ok(count)`` with the number of removed link rows (jsonc + registry).
        ``Err(FitsError)`` when artifacts cannot be read or written.
    """
    registry_path = root / _REGISTRY_PATH
    links_path = root / _LINKS_PATH
    if not registry_path.is_file() or not links_path.is_file():
        return Ok(0)

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        links_doc = _load_jsonc(links_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return Err(FitsError(str(exc), code="links_reconcile_failed"))

    links = links_doc.get("links", [])
    if not isinstance(links, list):
        return Err(
            FitsError("links file missing links array", code="links_reconcile_failed")
        )

    registered = _registered_guids(registry)
    node_guids = _registered_node_guids(registry)
    touching_logical = drop_touching_nodes or set()
    drop_touching_guids: set[str] = set()
    if touching_logical:
        index_result = InstanceIndex.load(root)
        if isinstance(index_result, Ok):
            drop_touching_guids = index_result.ok_value.guids_for_names(
                touching_logical
            )

    kept_links: list[dict[str, Any]] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        if _link_is_valid(
            item,
            registered=registered,
            node_guids=node_guids,
            drop_touching_guids=drop_touching_guids,
        ):
            kept_links.append(item)

    kept_link_guids = {
        link["guid"] for link in kept_links if isinstance(link.get("guid"), str)
    }
    removed_links = len(links) - len(kept_links)

    instances = registry.get("instances", [])
    if not isinstance(instances, list):
        instances = []

    kept_instances: list[dict[str, Any]] = []
    removed_registry = 0
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        if inst.get("kind") == "link" and inst.get("guid") not in kept_link_guids:
            removed_registry += 1
            continue
        kept_instances.append(inst)

    removed = removed_links + removed_registry
    if removed == 0:
        return Ok(0)

    links_doc["links"] = kept_links
    registry["instances"] = kept_instances

    try:
        links_path.write_text(
            json.dumps(links_doc, indent=2) + "\n",
            encoding="utf-8",
        )
        registry_path.write_text(
            json.dumps(registry, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return Err(FitsError(str(exc), code="links_reconcile_failed"))

    return Ok(removed)
