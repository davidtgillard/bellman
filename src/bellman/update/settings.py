"""Load update settings from $HOME/.bellman/bellman-settings.toml."""

from __future__ import annotations

import platform
import sys
import tomllib
from dataclasses import dataclass

from bellman.update.paths import settings_path

DEFAULT_REPOSITORY = "davidtgillard/bellman"
DEFAULT_RELEASE_TAG = "dev"
DEFAULT_CHECK_INTERVAL_HOURS = 24
DEFAULT_TIMEOUT_SECONDS = 10


def default_asset_pattern() -> str:
    """Return the GitHub release asset name pattern for this host platform.

    Returns:
        Pattern containing a ``{version}`` placeholder for the host OS/arch,
        or the Linux x86_64 pattern when the host is unsupported.
    """
    system = sys.platform
    machine = platform.machine().lower()
    if system.startswith("linux") and machine in ("x86_64", "amd64"):
        return "bellman-{version}-linux-x86_64"
    if system == "win32" and machine in ("x86_64", "amd64"):
        return "bellman-{version}-windows-x86_64.exe"
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "bellman-{version}-macos-arm64"
    return "bellman-{version}-linux-x86_64"


DEFAULT_ASSET_PATTERN = default_asset_pattern()


@dataclass(frozen=True)
class UpdateSettings:
    """Self-update configuration loaded from settings.toml.

    Attributes:
        check_interval_hours: Minimum hours between background update checks.
        timeout_seconds: HTTP timeout for GitHub API and downloads.
        repository: GitHub ``owner/repo`` that hosts release assets.
        release_tag: Release tag to poll (rolling ``dev`` by default).
        asset_pattern: Filename pattern with a ``{version}`` placeholder.
    """

    check_interval_hours: float
    timeout_seconds: float
    repository: str
    release_tag: str
    asset_pattern: str


def load_settings() -> UpdateSettings:
    """Load update settings from disk, falling back to platform defaults.

    Returns:
        Parsed settings, or defaults when the settings file is missing.
    """
    path = settings_path()
    pattern = default_asset_pattern()
    if not path.is_file():
        return UpdateSettings(
            check_interval_hours=DEFAULT_CHECK_INTERVAL_HOURS,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            repository=DEFAULT_REPOSITORY,
            release_tag=DEFAULT_RELEASE_TAG,
            asset_pattern=pattern,
        )
    with path.open("rb") as f:
        data = tomllib.load(f)
    section = data.get("update", {})
    return UpdateSettings(
        check_interval_hours=float(
            section.get("check_interval_hours", DEFAULT_CHECK_INTERVAL_HOURS)
        ),
        timeout_seconds=float(section.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        repository=str(section.get("repository", DEFAULT_REPOSITORY)),
        release_tag=str(section.get("release_tag", DEFAULT_RELEASE_TAG)),
        asset_pattern=str(section.get("asset_pattern", pattern)),
    )
