"""Plugin protocol and registration dataclass."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bellman.plugin.args import PluginArgumentSpecs

if TYPE_CHECKING:
    from bellman.plugin.arguments import PluginArguments
    from bellman.plugin.context import BellmanContext
    from bellman.plugin.textio import TextIO

__all__ = ["PluginRun", "BellmanPlugin"]

PluginRun = Callable[["BellmanContext", "PluginArguments", "TextIO"], int]
"""Plugin entry: context, parsed args, streams; returns process exit code."""


@dataclass(frozen=True, slots=True)
class BellmanPlugin:
    """Repo-local plugin registered under ``plugin/{name}/``."""

    name: str
    summary: str
    args: PluginArgumentSpecs
    run: PluginRun
