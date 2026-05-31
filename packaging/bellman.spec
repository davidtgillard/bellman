# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for bellman one-file binary."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH).resolve().parent
src = root / "src"

libfits_path = os.environ.get("LIBFITS_PATH", "")
binaries: list[tuple[str, str]] = []
if libfits_path and Path(libfits_path).is_file():
    binaries.append((libfits_path, "."))

a = Analysis(
    [str(src / "bellman" / "__main__.py")],
    pathex=[str(src)],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        "bellman",
        "bellman.cli",
        "bellman._version",
        "bellman._build_version",
        "bellman.update",
        "bellman.update.background",
        "bellman.update.check",
        "bellman.update.download",
        "bellman.update.github",
        "bellman.update.install",
        "bellman.update.paths",
        "bellman.update.settings",
        "bellman.update.state",
        "pyfits",
        "pyfits._native",
        "semver",
        "typer",
        "click",
        *collect_submodules("shellingham"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(root / "packaging" / "rthook_libfits.py"),
        str(root / "packaging" / "rthook_shellingham.py"),
    ],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="bellman",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
