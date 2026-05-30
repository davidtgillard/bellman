"""Discover repo-local plugins under ``plugin/``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["PluginSpec", "discover_plugins"]

_PLUGIN_DIR = "plugin"


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """Discovered plugin directory and entry module."""

    name: str
    path: Path
    module_name: str


def discover_plugins(root: Path) -> list[PluginSpec]:
    """List plugins under ``root/plugin/``.

    Each immediate child directory containing ``__init__.py`` or ``plugin.py``
    is one plugin. The directory name is the default CLI name.

    Args:
        root: Roadmap root directory.

    Returns:
        Sorted list of plugin specs (empty when ``plugin/`` is missing).
    """
    plugin_root = root / _PLUGIN_DIR
    if not plugin_root.is_dir():
        return []
    specs: list[PluginSpec] = []
    for child in sorted(plugin_root.iterdir()):
        if not child.is_dir():
            continue
        entry = _entry_module(child)
        if entry is None:
            continue
        specs.append(
            PluginSpec(
                name=child.name,
                path=child,
                module_name=f"snark_plugin_{child.name.replace('-', '_')}",
            )
        )
    return specs


def _entry_module(plugin_dir: Path) -> str | None:
    if (plugin_dir / "__init__.py").is_file():
        return "__init__"
    if (plugin_dir / "plugin.py").is_file():
        return "plugin"
    return None
