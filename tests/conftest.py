"""Shared fixtures for the bellman test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_update_state_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Avoid writing update state next to the test runner executable.

    Without this, ``state_write_path()`` prefers ``<exe_dir>/.bellman``, which
    for pytest is under ``.venv/bin`` and can leave a polluted or unwritable
    directory that breaks later CLI update tests.
    """
    home = tmp_path / "iso_home" / ".bellman"
    local = tmp_path / "iso_local" / ".bellman"
    home.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("bellman.update.paths.home_bellman_dir", lambda: home)
    monkeypatch.setattr("bellman.update.paths.local_bellman_dir", lambda: local)
    monkeypatch.setattr(
        "bellman.update.state.state_write_path",
        lambda: local / "bellman-state.json",
    )
    monkeypatch.setattr(
        "bellman.update.state.state_read_path",
        lambda: (
            (local / "bellman-state.json")
            if (local / "bellman-state.json").is_file()
            else (
                (home / "bellman-state.json")
                if (home / "bellman-state.json").is_file()
                else None
            )
        ),
    )
