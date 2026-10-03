"""Discover repo-local validators under ``validator/``."""

from __future__ import annotations

from pathlib import Path

from bellman.plugin.discover import PluginSpec

__all__ = ["VALIDATOR_DIR", "discover_validators"]

VALIDATOR_DIR = "validator"
"""Directory under the roadmap root that holds validators."""


def discover_validators(root: Path) -> list[PluginSpec]:
    """List validators under ``root/validator/``.

    Each immediate child directory containing ``__init__.py`` or ``plugin.py``
    is one validator; the directory name is the validator name.

    Args:
        root: Roadmap root directory.

    Returns:
        Sorted specs (empty when ``validator/`` is missing).
    """
    validator_root = root / VALIDATOR_DIR
    if not validator_root.is_dir():
        return []
    specs: list[PluginSpec] = []
    for child in sorted(validator_root.iterdir()):
        if not child.is_dir():
            continue
        if (
            not (child / "__init__.py").is_file()
            and not (child / "plugin.py").is_file()
        ):
            continue
        specs.append(
            PluginSpec(
                name=child.name,
                path=child,
                module_name=f"bellman_validator_{child.name.replace('-', '_')}",
            )
        )
    return specs
