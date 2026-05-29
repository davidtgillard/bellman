"""Resolve snark state and settings paths."""

from __future__ import annotations

import sys
from pathlib import Path

SNARK_DIR = ".snark"
STATE_FILENAME = "snark-state.json"
SETTINGS_FILENAME = "snark-settings.toml"


def executable_dir() -> Path:
    """Directory containing the snark executable (argv[0])."""
    return Path(sys.argv[0]).resolve().parent


def home_snark_dir() -> Path:
    return Path.home() / SNARK_DIR


def local_snark_dir() -> Path:
    return executable_dir() / SNARK_DIR


def settings_path() -> Path:
    """Settings always live under $HOME/.snark/."""
    return home_snark_dir() / SETTINGS_FILENAME


def state_read_path() -> Path | None:
    """Return existing state file path (local over home), or None."""
    local = local_snark_dir() / STATE_FILENAME
    if local.is_file():
        return local
    home = home_snark_dir() / STATE_FILENAME
    if home.is_file():
        return home
    return None


def state_write_path() -> Path:
    """Path for writing state (prefer most local writable location)."""
    local_dir = local_snark_dir()
    home_dir = home_snark_dir()
    for directory in (local_dir, home_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            test_file = directory / ".write_test"
            test_file.touch()
            test_file.unlink()
            return directory / STATE_FILENAME
        except OSError:
            continue
    return home_dir / STATE_FILENAME


def target_binary_path() -> Path:
    """Path to the running snark binary."""
    return Path(sys.argv[0]).resolve()
