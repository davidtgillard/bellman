"""Replace the running snark binary with a downloaded build."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

from snark.update.paths import target_binary_path
from snark.update.state import SnarkState


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def verify_update_permissions() -> Path:
    """Ensure the running binary can be replaced.

    Returns:
        Resolved path to the running snark binary.

    Raises:
        OSError: When the binary is missing or its directory is not writable.
    """
    target = target_binary_path()
    if not target.is_file():
        msg = f"cannot update: executable not found at {target}"
        raise OSError(msg)

    parent = target.parent
    if not os.access(parent, os.W_OK | os.X_OK):
        msg = f"cannot update: no write permission for directory {parent}"
        raise OSError(msg)

    try:
        fd, name = tempfile.mkstemp(prefix=".snark-perm-test-", dir=parent)
        os.close(fd)
        Path(name).unlink()
    except OSError as exc:
        msg = f"cannot update: cannot write to {parent}: {exc}"
        raise OSError(msg) from exc

    return target


def apply_binary_update(
    staging: Path,
    *,
    version: str,
    asset_id: int,
) -> None:
    target = target_binary_path()
    staging.chmod(staging.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(staging, target)
    state = SnarkState.load()
    state.installed_version = version
    state.installed_asset_id = asset_id
    state.save()
