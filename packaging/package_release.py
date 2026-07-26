#!/usr/bin/env python3
"""Copy the PyInstaller binary into a named release asset with a sha256 sidecar."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tomllib
from pathlib import Path

_PLATFORM_SUFFIX: dict[str, str] = {
    "linux-x86_64": "linux-x86_64",
    "windows-x86_64": "windows-x86_64.exe",
    "macos-arm64": "macos-arm64",
}


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str):
        msg = "project.version must be a string"
        raise SystemExit(msg)
    return version


def _binary_candidates(dist: Path) -> list[Path]:
    return [dist / "bellman.exe", dist / "bellman"]


def package(*, platform_id: str, root: Path | None = None) -> Path:
    """Stage ``dist/release/bellman-{version}-{platform}`` and its ``.sha256``.

    Args:
        platform_id: Matrix id (``linux-x86_64``, ``windows-x86_64``, or
            ``macos-arm64``).
        root: Repository root; defaults to the parent of ``packaging/``.

    Returns:
        Path to the staged binary asset.

    Raises:
        SystemExit: When the platform id is unknown or the binary is missing.
    """
    if platform_id not in _PLATFORM_SUFFIX:
        msg = (
            f"Unknown platform id {platform_id!r}; "
            f"expected one of {', '.join(sorted(_PLATFORM_SUFFIX))}"
        )
        raise SystemExit(msg)

    root = root or Path(__file__).resolve().parents[1]
    dist = root / "dist"
    binary: Path | None = None
    for candidate in _binary_candidates(dist):
        if candidate.is_file():
            binary = candidate
            break
    if binary is None:
        msg = f"PyInstaller binary not found under {dist}"
        raise SystemExit(msg)

    version = _project_version(root)
    asset_name = f"bellman-{version}-{_PLATFORM_SUFFIX[platform_id]}"
    release_dir = dist / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    asset_path = release_dir / asset_name
    shutil.copy2(binary, asset_path)
    asset_path.chmod(asset_path.stat().st_mode | 0o111)

    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    sidecar = release_dir / f"{asset_name}.sha256"
    sidecar.write_text(f"{digest}  {asset_name}\n", encoding="utf-8")
    return asset_path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        required=True,
        choices=sorted(_PLATFORM_SUFFIX),
        help="Release matrix platform id",
    )
    args = parser.parse_args()
    asset = package(platform_id=args.platform)
    print(asset)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code:
            sys.exit(exc.code)
