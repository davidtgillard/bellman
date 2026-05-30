"""Load repo-local plugin modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from snark.naming import validate_kebab
from snark.plugin.discover import PluginSpec, discover_plugins
from snark.plugin.protocol import SnarkPlugin

__all__ = ["PluginLoadError", "load_plugin", "list_plugins"]

PLUGIN_EXPORT = "PLUGIN"


class PluginLoadError(Exception):
    """Failure loading a plugin module."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path

    def format(self) -> str:
        if self.path is not None:
            return f"{self.path}: {self.message}"
        return self.message


def list_plugins(root: Path) -> list[SnarkPlugin]:
    """Discover and load all plugins under ``root/plugin/``.

    Args:
        root: Roadmap root directory.

    Returns:
        Loaded plugins in discovery order. Plugins that fail to load are
        omitted; use :func:`load_plugin` for explicit error reporting.
    """
    plugins: list[SnarkPlugin] = []
    for spec in discover_plugins(root):
        loaded = load_plugin(root, spec.name)
        if loaded is not None:
            plugins.append(loaded)
    return plugins


def load_plugin(root: Path, name: str) -> SnarkPlugin | None:
    """Load a single plugin by CLI name.

    Args:
        root: Roadmap root directory.
        name: Plugin directory name (kebab-case).

    Returns:
        The registered :class:`SnarkPlugin`, or ``None`` when not found.

    Raises:
        PluginLoadError: When import or registration fails (as exception via
            :func:`load_plugin_or_raise`).
    """
    try:
        return load_plugin_or_raise(root, name)
    except PluginLoadError:
        return None


def load_plugin_or_raise(root: Path, name: str) -> SnarkPlugin:
    """Load a plugin or raise :class:`PluginLoadError`.

    Args:
        root: Roadmap root directory.
        name: Plugin directory name.

    Returns:
        Validated :class:`SnarkPlugin`.

    Raises:
        PluginLoadError: When the plugin is missing or invalid.
    """
    try:
        validate_kebab(name)
    except ValueError as exc:
        raise PluginLoadError(str(exc)) from exc

    spec = _spec_for_name(root, name)
    if spec is None:
        available = ", ".join(s.name for s in discover_plugins(root)) or "(none)"
        msg = f"unknown plugin {name!r}; available: {available}"
        raise PluginLoadError(msg)

    module = _import_plugin(spec)
    plugin_obj = getattr(module, PLUGIN_EXPORT, None)
    if not isinstance(plugin_obj, SnarkPlugin):
        msg = f"module must define {PLUGIN_EXPORT} as SnarkPlugin"
        raise PluginLoadError(msg, path=str(spec.path))

    if plugin_obj.name != spec.name:
        msg = f"plugin name {plugin_obj.name!r} does not match directory {spec.name!r}"
        raise PluginLoadError(msg, path=str(spec.path))

    try:
        validate_kebab(plugin_obj.name)
    except ValueError as exc:
        raise PluginLoadError(str(exc), path=str(spec.path)) from exc

    return plugin_obj


def _spec_for_name(root: Path, name: str) -> PluginSpec | None:
    for spec in discover_plugins(root):
        if spec.name == name:
            return spec
    return None


def _import_plugin(spec: PluginSpec) -> ModuleType:
    init_file = spec.path / "__init__.py"
    plugin_file = spec.path / "plugin.py"
    if init_file.is_file():
        file_path = init_file
    elif plugin_file.is_file():
        file_path = plugin_file
    else:
        msg = "no __init__.py or plugin.py"
        raise PluginLoadError(msg, path=str(spec.path))

    spec_obj = importlib.util.spec_from_file_location(
        spec.module_name,
        file_path,
        submodule_search_locations=[str(spec.path)],
    )
    if spec_obj is None or spec_obj.loader is None:
        msg = "cannot create module spec"
        raise PluginLoadError(msg, path=str(file_path))

    module = importlib.util.module_from_spec(spec_obj)
    sys.modules[spec.module_name] = module
    try:
        spec_obj.loader.exec_module(module)
    except Exception as exc:
        msg = f"import failed: {exc}"
        raise PluginLoadError(msg, path=str(file_path)) from exc
    return module
