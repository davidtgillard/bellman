"""Package version loaded from installed metadata and validated with semver."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import semver

_FALLBACK_VERSION = "0.0.0+unknown"


def _load_version_string() -> str:
    try:
        return version("snark")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


_VERSION_STRING = _load_version_string()
_VERSION = semver.Version.parse(_VERSION_STRING)


def get_version() -> semver.Version:
    """Return the installed snark version as a semver object."""
    return _VERSION


def version_string() -> str:
    """Return the installed snark version string."""
    return _VERSION_STRING
