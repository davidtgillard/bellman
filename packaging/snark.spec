# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for snark one-file binary."""

import os
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent
src = root / "src"

libfits_path = os.environ.get("LIBFITS_PATH", "")
binaries: list[tuple[str, str]] = []
if libfits_path and Path(libfits_path).is_file():
    binaries.append((libfits_path, "."))

a = Analysis(
    [str(src / "snark" / "__main__.py")],
    pathex=[str(src)],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        "snark",
        "snark.cli",
        "snark._version",
        "snark._build_version",
        "snark.update",
        "snark.update.background",
        "snark.update.check",
        "snark.update.download",
        "snark.update.github",
        "snark.update.install",
        "snark.update.paths",
        "snark.update.settings",
        "snark.update.state",
        "pyfits",
        "pyfits._native",
        "semver",
        "typer",
        "click",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / "packaging" / "rthook_libfits.py")],
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
    name="snark",
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
