"""Load update settings from $HOME/.bellman/bellman-settings.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

from bellman.update.paths import settings_path

DEFAULT_REPOSITORY = "davidtgillard/bellman"
DEFAULT_RELEASE_TAG = "dev"
DEFAULT_CHECK_INTERVAL_HOURS = 24
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_ASSET_PATTERN = "bellman-{version}-linux-x86_64"


@dataclass(frozen=True)
class UpdateSettings:
    check_interval_hours: float
    timeout_seconds: float
    repository: str
    release_tag: str
    asset_pattern: str


def load_settings() -> UpdateSettings:
    path = settings_path()
    if not path.is_file():
        return UpdateSettings(
            check_interval_hours=DEFAULT_CHECK_INTERVAL_HOURS,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            repository=DEFAULT_REPOSITORY,
            release_tag=DEFAULT_RELEASE_TAG,
            asset_pattern=DEFAULT_ASSET_PATTERN,
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
        asset_pattern=str(section.get("asset_pattern", DEFAULT_ASSET_PATTERN)),
    )
