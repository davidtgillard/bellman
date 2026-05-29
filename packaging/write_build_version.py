#!/usr/bin/env python3
"""Write src/snark/_build_version.py from pyproject.toml version."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    with pyproject.open("rb") as f:
        version = tomllib.load(f)["project"]["version"]
    out = root / "src" / "snark" / "_build_version.py"
    header = (
        '"""Embedded version for PyInstaller builds '
        '(overwritten at release build time)."""\n\n'
    )
    out.write_text(header + f'VERSION = "{version}"\n', encoding="utf-8")
    print(f"Wrote {out} with VERSION = {version!r}")


if __name__ == "__main__":
    main()
    sys.exit(0)
