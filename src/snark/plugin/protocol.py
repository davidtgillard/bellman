"""Plugin protocol and registration dataclass."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from snark.plugin.args import PluginArgumentSpecs

if TYPE_CHECKING:
    from snark.plugin.arguments import PluginArguments
    from snark.plugin.context import SnarkContext
    from snark.plugin.textio import TextIO

__all__ = ["PluginRun", "SnarkPlugin"]

PluginRun = Callable[["SnarkContext", "PluginArguments", "TextIO"], int]
"""Plugin entry: context, parsed args, streams; returns process exit code."""


@dataclass(frozen=True, slots=True)
class SnarkPlugin:
    """Repo-local plugin registered under ``plugin/{name}/``."""

    name: str
    summary: str
    args: PluginArgumentSpecs
    run: PluginRun
