"""Declarative argparse specs for repo-local plugins."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "FlagSpec",
    "OptionSpec",
    "PositionalSpec",
    "PluginArgumentSpecs",
    "build_parser",
]

_DEST_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


@dataclass(frozen=True, slots=True)
class FlagSpec:
    """Boolean flag (``store_true``)."""

    name: str
    help: str = ""
    default: bool = False


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """Optional or required option with a string value."""

    name: str
    help: str = ""
    default: str | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class PositionalSpec:
    """Positional argument."""

    name: str
    help: str = ""
    nargs: Literal["?", "*", "+"] | int = "?"
    default: str | None = None


@dataclass(frozen=True, slots=True)
class PluginArgumentSpecs:
    """Argument specifications for a single plugin command."""

    specs: tuple[FlagSpec | OptionSpec | PositionalSpec, ...] = ()

    def __post_init__(self) -> None:
        dests: list[str] = []
        for spec in self.specs:
            dest = _dest_for(spec)
            if dest in dests:
                msg = f"duplicate argument dest {dest!r}"
                raise ValueError(msg)
            dests.append(dest)

    @staticmethod
    def empty() -> PluginArgumentSpecs:
        """Return specs with no arguments."""
        return PluginArgumentSpecs(())


def _dest_for(spec: FlagSpec | OptionSpec | PositionalSpec) -> str:
    if isinstance(spec, PositionalSpec):
        return spec.name
    raw = spec.name.lstrip("-").replace("-", "_")
    if not _DEST_RE.fullmatch(raw):
        msg = f"invalid argument name {spec.name!r}"
        raise ValueError(msg)
    return raw


def _long_option(name: str) -> str:
    if name.startswith("--"):
        return name
    if name.startswith("-"):
        return f"-{name}"
    return f"--{name}"


def build_parser(
    plugin_name: str,
    summary: str,
    specs: PluginArgumentSpecs,
) -> argparse.ArgumentParser:
    """Build an :class:`argparse.ArgumentParser` from plugin specs.

    Args:
        plugin_name: Plugin CLI name (used in prog).
        summary: One-line description for help text.
        specs: Declarative argument list.

    Returns:
        Parser configured for ``parse_args`` on trailing plugin argv.
    """
    parser = argparse.ArgumentParser(
        prog=f"snark plugin {plugin_name}",
        description=summary,
    )
    for spec in specs.specs:
        if isinstance(spec, FlagSpec):
            parser.add_argument(
                _long_option(spec.name),
                action="store_true",
                default=spec.default,
                help=spec.help,
            )
        elif isinstance(spec, OptionSpec):
            parser.add_argument(
                _long_option(spec.name),
                default=spec.default,
                required=spec.required,
                help=spec.help,
            )
        elif isinstance(spec, PositionalSpec):
            parser.add_argument(
                spec.name,
                nargs=spec.nargs,
                default=spec.default,
                help=spec.help,
            )
    return parser
