"""PyInstaller runtime hook: preload shellingham for Typer shell detection."""

from __future__ import annotations

import sys

if getattr(sys, "frozen", False):
    import shellingham.posix  # noqa: F401
