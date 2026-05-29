"""Fetch GitHub release metadata."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

import semver

from snark.update.settings import UpdateSettings

_ASSET_VERSION_RE = re.compile(r"snark-(.+?)-linux-x86_64(?:\.sha256)?$")


@dataclass(frozen=True)
class ReleaseAsset:
    id: int
    name: str
    url: str
    browser_download_url: str
    updated_at: str


@dataclass(frozen=True)
class GitHubRelease:
    tag_name: str
    assets: tuple[ReleaseAsset, ...]


def _parse_asset(raw: dict[str, object]) -> ReleaseAsset | None:
    name = raw.get("name")
    if not isinstance(name, str) or name.endswith(".sha256"):
        return None
    asset_id = raw.get("id")
    url = raw.get("url")
    browser = raw.get("browser_download_url")
    updated = raw.get("updated_at")
    if not isinstance(asset_id, int) or not isinstance(url, str):
        return None
    if not isinstance(browser, str) or not isinstance(updated, str):
        return None
    return ReleaseAsset(
        id=asset_id,
        name=name,
        url=url,
        browser_download_url=browser,
        updated_at=updated,
    )


def fetch_release(settings: UpdateSettings) -> GitHubRelease:
    api_url = (
        f"https://api.github.com/repos/{settings.repository}"
        f"/releases/tags/{settings.release_tag}"
    )
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "snark-updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        msg = f"failed to fetch release: {exc}"
        raise OSError(msg) from exc

    tag = data.get("tag_name", settings.release_tag)
    if not isinstance(tag, str):
        tag = settings.release_tag
    raw_assets = data.get("assets", [])
    assets: list[ReleaseAsset] = []
    if isinstance(raw_assets, list):
        for item in raw_assets:
            if isinstance(item, dict):
                parsed = _parse_asset(item)
                if parsed is not None:
                    assets.append(parsed)
    return GitHubRelease(tag_name=tag, assets=tuple(assets))


def parse_version_from_asset_name(name: str) -> str | None:
    match = _ASSET_VERSION_RE.match(name)
    if match:
        return match.group(1)
    return None


def pick_linux_asset(
    release: GitHubRelease, settings: UpdateSettings, version: str
) -> ReleaseAsset | None:
    expected = settings.asset_pattern.format(version=version)
    for asset in release.assets:
        if asset.name == expected:
            return asset
    for asset in release.assets:
        if parse_version_from_asset_name(asset.name) == version:
            return asset
    return None


def latest_linux_asset(release: GitHubRelease) -> ReleaseAsset | None:
    candidates: list[tuple[semver.Version, ReleaseAsset]] = []
    for asset in release.assets:
        ver = parse_version_from_asset_name(asset.name)
        if ver is None:
            continue
        try:
            candidates.append((semver.Version.parse(ver), asset))
        except ValueError:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]
