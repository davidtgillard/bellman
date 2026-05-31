"""``python -m bellman`` entry point."""

from __future__ import annotations

import sys

if getattr(sys, "frozen", False):
    import shellingham.posix  # noqa: F401  # type: ignore[import-untyped]

from bellman.cli import app

app()
