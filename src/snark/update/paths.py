"""Resolve snark state and settings paths."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SNARK_DIR = ".snark"
STATE_FILENAME = "snark-state.json"
SETTINGS_FILENAME = "snark-settings.toml"


def running_executable() -> Path:
    """Path to the running snark executable.

    ``sys.argv[0]`` is often a bare command name (for example ``snark``) when
    the binary is on ``PATH``, which would resolve relative to the current
    working directory. Prefer ``sys.executable`` for PyInstaller builds and
    ``shutil.which`` for bare names before falling back to ``argv[0]``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()

    argv0 = Path(sys.argv[0])
    if argv0.is_absolute() or argv0.parent != Path("."):
        return argv0.resolve()

    found = shutil.which(sys.argv[0])
    if found is not None:
        return Path(found).resolve()

    proc_exe = Path("/proc/self/exe")
    if proc_exe.is_symlink():
        return proc_exe.resolve()

    return argv0.resolve()


def executable_dir() -> Path:
    """Directory containing the snark executable."""
    return running_executable().parent


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
    return running_executable()
