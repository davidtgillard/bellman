#!/usr/bin/env python3
"""Print path to libfits.so for PyInstaller bundling."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _from_env() -> Path | None:
    raw = os.environ.get("LIBFITS_PATH", "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def _from_pyfits() -> Path | None:
    try:
        from pyfits._native import load_library
        from pyfits.result import Ok
    except ImportError:
        return None
    result = load_library()
    if not isinstance(result, Ok):
        return None
    lib = result.ok_value
    path_attr = getattr(lib, "_name", None) or getattr(lib, "name", None)
    if path_attr:
        path = Path(str(path_attr))
        if path.is_file():
            return path
    return None


def _search_common_paths() -> Path | None:
    candidates = [
        Path("../fits/target/release/libfits.so"),
        Path("../fits/libfits.so"),
        Path("/usr/local/lib/libfits.so"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def main() -> None:
    for resolver in (_from_env, _from_pyfits, _search_common_paths):
        found = resolver()
        if found is not None:
            print(found)
            return
    print(
        "libfits.so not found; set LIBFITS_PATH or build ../fits",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
