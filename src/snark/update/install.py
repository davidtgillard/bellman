"""Replace the running snark binary with a downloaded build."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from snark.update.paths import target_binary_path
from snark.update.state import SnarkState


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


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
