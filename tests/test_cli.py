"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from snark.cli import app

runner = CliRunner()


def test_init_and_create(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    result = runner.invoke(
        app,
        ["create", "initiative", "my-init", "--path", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert (tmp_path / "initiatives" / "my-init.md").is_file()
