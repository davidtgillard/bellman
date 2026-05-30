"""Execution context passed to repo-local plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyfits import Repo
from pyfits.errors import FitsError
from pyfits.models import Graph
from pyfits.result import Err, Ok, Result

from snark._version import version_string
from snark.graph import sync as graph_sync
from snark.graph.history import GraphHistory, load_graph_history
from snark.model import Roadmap
from snark.roadmap import load

__all__ = ["SnarkContext"]


@dataclass
class SnarkContext:
    """Lazy access to roadmap markdown, pyfits graph, and registry history.

    Attributes:
        root: Resolved roadmap root directory.
        snark_version: Installed snark version string.
        libfits_available: Whether the native libfits library can be loaded.
    """

    root: Path
    snark_version: str = field(default_factory=version_string)
    libfits_available: bool = field(default_factory=graph_sync.libfits_available)
    _roadmap: Roadmap | None = field(default=None, repr=False)
    _repo: Repo | None = field(default=None, repr=False)
    _graph: Graph | None = field(default=None, repr=False)
    _history: GraphHistory | None = field(default=None, repr=False)
    _repo_owned: bool = field(default=False, repr=False)

    def roadmap(self) -> Roadmap:
        """Load and cache the markdown roadmap model.

        Returns:
            Parsed :class:`~snark.model.Roadmap` for :attr:`root`.
        """
        if self._roadmap is None:
            self._roadmap = load(self.root)
        return self._roadmap

    def repo(self) -> Repo:
        """Open and cache a pyfits repository session.

        Returns:
            Open :class:`pyfits.Repo` for :attr:`root`.

        Raises:
            RuntimeError: When libfits is unavailable or open fails.
        """
        if self._repo is None:
            if not self.libfits_available:
                msg = "libfits not available; set PYFITS_LIB_PATH or build libfits"
                raise RuntimeError(msg)
            open_result = Repo.open(self.root)
            if isinstance(open_result, Err):
                msg = str(open_result.err_value)
                raise RuntimeError(msg) from None
            self._repo = open_result.ok_value
            self._repo_owned = True
        return self._repo

    def graph(self) -> Graph:
        """Return the current output graph (opens repo on first use).

        Returns:
            Graph from :meth:`pyfits.Repo.output_graph`.

        Raises:
            RuntimeError: When libfits is unavailable or the operation fails.
        """
        if self._graph is None:
            repo = self.repo()
            graph_result = repo.output_graph()
            if isinstance(graph_result, Err):
                msg = str(graph_result.err_value)
                raise RuntimeError(msg) from None
            self._graph = graph_result.ok_value
        return self._graph

    def history(self) -> GraphHistory:
        """Load and cache registry audit history.

        Returns:
            :class:`~snark.graph.history.GraphHistory` from ``.fits/registry.json``.

        Raises:
            RuntimeError: When the registry is missing or invalid.
        """
        if self._history is None:
            result = load_graph_history(self.root)
            if isinstance(result, Err):
                raise RuntimeError(result.err_value.format()) from None
            self._history = result.ok_value
        return self._history

    def sync_roadmap(self, *, prune: bool = False) -> Result[None, FitsError]:
        """Sync markdown roadmap into the pyfits graph at :attr:`root`.

        Args:
            prune: When ``True``, prune stale graph objects (same as CLI).

        Returns:
            ``Ok(None)`` on success, or ``Err(FitsError)`` on failure.
        """
        sync_result = graph_sync.sync_roadmap(self.root, prune=prune)
        if isinstance(sync_result, Ok):
            self._graph = None
        return sync_result

    def close(self) -> None:
        """Close an owned repository session if still open."""
        if self._repo_owned and self._repo is not None:
            self._repo.close()
            self._repo = None
            self._repo_owned = False
