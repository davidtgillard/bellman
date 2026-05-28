"""Snark: markdown-first roadmap planning on pyfits."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("snark")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
