"""Parsed plugin command-line arguments."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

__all__ = ["PluginArguments"]


class PluginArguments:
    """Attribute- and mapping-style access to parsed plugin argv."""

    def __init__(self, namespace: Namespace) -> None:
        """Wrap an argparse namespace.

        Args:
            namespace: Result of :meth:`argparse.ArgumentParser.parse_args`.
        """
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        """Return a parsed value by dest name (underscores, not dashes).

        Args:
            name: Argument dest (e.g. ``verbose`` for ``--verbose``).

        Returns:
            Parsed value from the namespace.

        Raises:
            AttributeError: When ``name`` is not present on the namespace.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return getattr(self._namespace, name)
        except AttributeError as exc:
            msg = f"'PluginArguments' object has no attribute {name!r}"
            raise AttributeError(msg) from exc

    def __getitem__(self, name: str) -> Any:
        """Return a parsed value by exact namespace attribute name.

        Args:
            name: Namespace attribute name.

        Returns:
            Parsed value.

        Raises:
            KeyError: When ``name`` is not on the namespace.
        """
        try:
            return getattr(self._namespace, name)
        except AttributeError as exc:
            raise KeyError(name) from exc
