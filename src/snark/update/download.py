"""Download release assets."""

from __future__ import annotations

import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from snark.update.github import ReleaseAsset
from snark.update.paths import target_binary_path
from snark.update.settings import UpdateSettings


def download_asset(asset: ReleaseAsset, *, settings: UpdateSettings) -> Path:
    """Download asset to a staging file on the same filesystem as the binary."""
    target = target_binary_path()
    target_dir = target.parent
    fd, staging_name = tempfile.mkstemp(
        prefix=".snark-download-",
        suffix=".tmp",
        dir=target_dir,
    )
    staging = Path(staging_name)
    try:
        request = urllib.request.Request(
            asset.browser_download_url,
            headers={"User-Agent": "snark-updater"},
        )
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as resp:
            with open(fd, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
    except (urllib.error.URLError, OSError) as exc:
        staging.unlink(missing_ok=True)
        msg = f"download failed: {exc}"
        raise OSError(msg) from exc
    else:
        return staging
