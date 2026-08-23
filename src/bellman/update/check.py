"""Compare installed bellman with GitHub dev release."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import semver
import typer

from bellman._version import get_version, version_string
from bellman.update.download import download_asset
from bellman.update.github import (
    ReleaseAsset,
    fetch_release,
    latest_platform_asset,
    parse_version_from_asset_name,
)
from bellman.update.install import (
    apply_binary_update,
    is_frozen,
    verify_update_permissions,
)
from bellman.update.settings import UpdateSettings, load_settings
from bellman.update.state import BellmanState


@dataclass(frozen=True)
class CheckResult:
    kind: Literal["up_to_date", "update_available", "check_failed"]
    message: str
    latest_version: str | None = None
    asset: ReleaseAsset | None = None


def _is_update_available(
    installed_version: semver.Version,
    installed_asset_id: int | None,
    latest_version: semver.Version,
    latest_asset: ReleaseAsset,
) -> bool:
    if latest_version > installed_version:
        return True
    if latest_version < installed_version:
        return False
    if installed_asset_id is None:
        return True
    return latest_asset.id != installed_asset_id


def _format_update_available_message(version_str: str, asset: ReleaseAsset) -> str:
    """Format the one-line update-available notice with digest and timestamp."""
    parts = [f"asset {asset.name}"]
    if asset.digest:
        parts.append(asset.digest)
    if asset.updated_at:
        parts.append(f"updated {asset.updated_at}")
    return f"update available: {version_str} ({', '.join(parts)})"


def check_for_update(
    *,
    settings: UpdateSettings | None = None,
    state: BellmanState | None = None,
    record_check: bool = True,
) -> CheckResult:
    settings = settings or load_settings()
    state = state if state is not None else BellmanState.load()
    installed = get_version()
    installed_asset_id = state.installed_asset_id

    try:
        release = fetch_release(settings)
        asset = latest_platform_asset(release, settings)
    except OSError as exc:
        if record_check:
            state.touch_check_time()
        return CheckResult(
            kind="check_failed",
            message=str(exc),
        )

    if asset is None:
        if record_check:
            state.touch_check_time()
        return CheckResult(
            kind="check_failed",
            message="no matching release asset found",
        )

    version_str = parse_version_from_asset_name(asset.name)
    if version_str is None:
        if record_check:
            state.touch_check_time()
        return CheckResult(
            kind="check_failed",
            message=f"could not parse version from asset {asset.name!r}",
        )

    try:
        latest = semver.Version.parse(version_str)
    except ValueError:
        if record_check:
            state.touch_check_time()
        return CheckResult(
            kind="check_failed",
            message=f"invalid semver in asset name: {version_str!r}",
        )

    if record_check:
        state.touch_check_time()

    if _is_update_available(installed, installed_asset_id, latest, asset):
        return CheckResult(
            kind="update_available",
            message=_format_update_available_message(version_str, asset),
            latest_version=version_str,
            asset=asset,
        )

    return CheckResult(
        kind="up_to_date",
        message=f"Bellman {version_string()} is up to date",
        latest_version=version_str,
        asset=asset,
    )


def should_run_background_check(state: BellmanState, settings: UpdateSettings) -> bool:
    if state.last_update_check is None:
        return True
    from datetime import UTC, datetime, timedelta

    elapsed = datetime.now(UTC) - state.last_update_check.astimezone(UTC)
    return elapsed >= timedelta(hours=settings.check_interval_hours)


def run_update_command(*, check_only: bool) -> None:
    result = check_for_update(record_check=True)

    if result.kind == "check_failed":
        typer.echo(result.message, err=True)
        raise typer.Exit(code=1)

    if result.kind == "up_to_date":
        typer.echo(result.message)
        raise typer.Exit(code=0)

    assert result.asset is not None
    assert result.latest_version is not None
    typer.echo(result.message)

    if check_only:
        raise typer.Exit(code=1)

    if not is_frozen():
        typer.echo(
            "Self-update applies to the PyInstaller binary; "
            "use the release from GitHub or rebuild with uv sync in development.",
            err=True,
        )
        raise typer.Exit(code=1)

    settings = load_settings()
    try:
        verify_update_permissions()
        staging = download_asset(result.asset, settings=settings)
        apply_binary_update(
            staging,
            version=result.latest_version,
            asset_id=result.asset.id,
        )
    except OSError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    updated_parts = [result.latest_version]
    if result.asset.digest:
        updated_parts.append(result.asset.digest)
    if result.asset.updated_at:
        updated_parts.append(f"updated {result.asset.updated_at}")
    typer.echo(f"Updated bellman to {', '.join(updated_parts)}")
