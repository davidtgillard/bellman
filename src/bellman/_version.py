"""Package version loaded from installed metadata and validated with semver."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import semver

_FALLBACK_VERSION = "0.0.0+unknown"


def _frozen_version_string() -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    try:
        from bellman._build_version import VERSION

        if VERSION:
            return VERSION
    except ImportError:
        pass
    return None


def _load_version_string() -> str:
    frozen = _frozen_version_string()
    if frozen is not None:
        return frozen
    try:
        return version("bellman")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


_VERSION_STRING = _load_version_string()
_VERSION = semver.Version.parse(_VERSION_STRING)


def get_version() -> semver.Version:
    """Return the installed bellman version as a semver object."""
    return _VERSION


def version_string() -> str:
    """Return the installed bellman version string."""
    return _VERSION_STRING
