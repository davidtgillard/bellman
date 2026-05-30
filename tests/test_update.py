"""Tests for self-update logic."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import semver
from typer.testing import CliRunner

from snark.cli import app
from snark.update.check import (
    CheckResult,
    _is_update_available,
    check_for_update,
    should_run_background_check,
)
from snark.update.github import GitHubRelease, ReleaseAsset, latest_linux_asset
from snark.update.install import is_frozen, verify_update_permissions
from snark.update.paths import (
    running_executable,
    settings_path,
    state_write_path,
    target_binary_path,
)
from snark.update.settings import UpdateSettings
from snark.update.state import SnarkState

runner = CliRunner()
V0_1_0 = semver.Version.parse("0.1.0")


def _asset(asset_id: int, version: str) -> ReleaseAsset:
    name = f"snark-{version}-linux-x86_64"
    return ReleaseAsset(
        id=asset_id,
        name=name,
        url=f"https://api.github.com/assets/{asset_id}",
        browser_download_url=f"https://example.com/{name}",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_is_update_available_newer_version() -> None:
    installed = semver.Version.parse("0.1.0")
    latest = semver.Version.parse("0.2.0")
    assert _is_update_available(installed, 100, latest, _asset(200, "0.2.0"))


def test_is_update_available_same_version_new_asset() -> None:
    installed = semver.Version.parse("0.1.0")
    latest = semver.Version.parse("0.1.0")
    assert _is_update_available(installed, 100, latest, _asset(200, "0.1.0"))


def test_is_update_available_up_to_date() -> None:
    installed = semver.Version.parse("0.2.0")
    latest = semver.Version.parse("0.2.0")
    assert not _is_update_available(installed, 200, latest, _asset(200, "0.2.0"))


def test_latest_linux_asset_picks_highest_semver() -> None:
    release = GitHubRelease(
        tag_name="dev",
        assets=(
            _asset(100, "0.1.0"),
            _asset(200, "0.2.0"),
            _asset(150, "0.1.5"),
        ),
    )
    asset = latest_linux_asset(release)
    assert asset is not None
    assert asset.id == 200


@patch("snark.update.check.fetch_release")
def test_check_for_update_available(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(200, "0.2.0"),),
    )
    state = SnarkState(installed_version="0.1.0", installed_asset_id=100)
    settings = UpdateSettings(
        check_interval_hours=24,
        timeout_seconds=5,
        repository="davidtgillard/snark",
        release_tag="dev",
        asset_pattern="snark-{version}-linux-x86_64",
    )
    with patch("snark.update.check.get_version", return_value=V0_1_0):
        result = check_for_update(settings=settings, state=state, record_check=False)
    assert result.kind == "update_available"
    assert result.latest_version == "0.2.0"


@patch("snark.update.check.fetch_release")
def test_check_for_update_up_to_date(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(100, "0.1.0"),),
    )
    state = SnarkState(installed_version="0.1.0", installed_asset_id=100)
    settings = UpdateSettings(
        check_interval_hours=24,
        timeout_seconds=5,
        repository="davidtgillard/snark",
        release_tag="dev",
        asset_pattern="snark-{version}-linux-x86_64",
    )
    with patch("snark.update.check.get_version", return_value=V0_1_0):
        result = check_for_update(settings=settings, state=state, record_check=False)
    assert result.kind == "up_to_date"


def test_should_run_background_check_interval() -> None:
    settings = UpdateSettings(
        check_interval_hours=24,
        timeout_seconds=5,
        repository="davidtgillard/snark",
        release_tag="dev",
        asset_pattern="snark-{version}-linux-x86_64",
    )
    assert should_run_background_check(SnarkState(), settings)
    recent = SnarkState(last_update_check=datetime.now(UTC) - timedelta(hours=1))
    assert not should_run_background_check(recent, settings)
    stale = SnarkState(last_update_check=datetime.now(UTC) - timedelta(hours=25))
    assert should_run_background_check(stale, settings)


def test_state_path_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "snark-bin")])
    monkeypatch.setattr(
        "snark.update.paths.home_snark_dir",
        lambda: tmp_path / "home-snark",
    )
    monkeypatch.setattr(
        "snark.update.paths.local_snark_dir",
        lambda: tmp_path / "local-snark",
    )
    local_state = tmp_path / "local-snark" / "snark-state.json"
    home_state = tmp_path / "home-snark" / "snark-state.json"
    local_state.parent.mkdir(parents=True)
    home_state.parent.mkdir(parents=True)
    local_state.write_text('{"installed_version": "local"}', encoding="utf-8")
    home_state.write_text('{"installed_version": "home"}', encoding="utf-8")
    monkeypatch.setattr(
        "snark.update.state.state_read_path",
        lambda: local_state if local_state.is_file() else home_state,
    )
    loaded = SnarkState.load()
    assert loaded.installed_version == "local"


def test_state_write_local_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "snark-bin")])
    monkeypatch.setattr(
        "snark.update.paths.executable_dir",
        lambda: tmp_path / "bin",
    )
    monkeypatch.setattr(
        "snark.update.paths.home_snark_dir",
        lambda: tmp_path / "home-snark",
    )
    monkeypatch.setattr(
        "snark.update.paths.local_snark_dir",
        lambda: tmp_path / "bin" / ".snark",
    )
    write_path = state_write_path()
    assert write_path == tmp_path / "bin" / ".snark" / "snark-state.json"


@patch("snark.update.background.check_for_update")
@patch("snark.update.check.fetch_release")
def test_background_skips_update_subcommand(
    mock_fetch: MagicMock,
    mock_bg_check: MagicMock,
) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(100, "0.1.0"),),
    )
    state = SnarkState(installed_version="0.1.0", installed_asset_id=100)
    with (
        patch("snark.update.check.get_version", return_value=V0_1_0),
        patch("snark.update.check.SnarkState.load", return_value=state),
    ):
        result = runner.invoke(app, ["update", "--check"])
    mock_bg_check.assert_not_called()
    assert result.exit_code == 0


@patch("snark.update.background.check_for_update")
def test_background_notifies_when_update_available(mock_check: MagicMock) -> None:
    mock_check.return_value = CheckResult(
        kind="update_available",
        message="update available",
        latest_version="0.2.0",
    )
    with patch(
        "snark.update.background.should_run_background_check",
        return_value=True,
    ):
        result = runner.invoke(app, ["version"])
    combined = result.stdout + result.stderr
    assert "snark update" in combined
    mock_check.assert_called_once()


@patch("snark.update.check.fetch_release")
def test_cli_update_check_exit_code(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(200, "0.2.0"),),
    )
    with patch("snark.update.check.get_version", return_value=V0_1_0):
        result = runner.invoke(app, ["update", "--check"])
    assert result.exit_code == 1
    assert "update available" in result.stdout.lower() or "0.2.0" in result.stdout


@patch("snark.update.check.fetch_release")
def test_cli_update_check_up_to_date(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(100, "0.1.0"),),
    )
    state = SnarkState(installed_version="0.1.0", installed_asset_id=100)
    with (
        patch("snark.update.check.get_version", return_value=V0_1_0),
        patch("snark.update.check.SnarkState.load", return_value=state),
    ):
        result = runner.invoke(app, ["update", "--check"])
    assert result.exit_code == 0


def test_cli_update_apply_requires_frozen() -> None:
    with (
        patch("snark.update.check.fetch_release") as mock_fetch,
        patch("snark.update.check.get_version", return_value=V0_1_0),
        patch("snark.update.install.is_frozen", return_value=False),
    ):
        mock_fetch.return_value = GitHubRelease(
            tag_name="dev",
            assets=(_asset(200, "0.2.0"),),
        )
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "PyInstaller" in result.stderr or "development" in result.stderr


def test_settings_path_under_home() -> None:
    assert settings_path().name == "snark-settings.toml"
    assert settings_path().parent.name == ".snark"


def test_state_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "snark-state.json"
    monkeypatch.setattr("snark.update.state.state_write_path", lambda: state_file)
    monkeypatch.setattr(
        "snark.update.state.state_read_path",
        lambda: state_file if state_file.is_file() else None,
    )
    state = SnarkState(
        last_update_check=datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
        installed_version="0.1.0",
        installed_asset_id=42,
    )
    state.save()
    loaded = SnarkState.load()
    assert loaded.installed_version == "0.1.0"
    assert loaded.installed_asset_id == 42
    assert loaded.last_update_check is not None


def test_is_frozen_false_in_tests() -> None:
    assert not is_frozen()


def test_running_executable_frozen_uses_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "bin" / "snark"
    binary.parent.mkdir()
    binary.write_bytes(b"fake")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    monkeypatch.setattr(sys, "argv", ["snark"])
    assert running_executable() == binary.resolve()
    assert target_binary_path() == binary.resolve()


def test_running_executable_bare_name_uses_which(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "snark"
    binary.write_bytes(b"fake")
    binary.chmod(0o755)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["snark"])
    monkeypatch.setenv("PATH", str(tmp_path))
    assert running_executable() == binary.resolve()


def test_verify_update_permissions_requires_writable_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "snark"
    binary.write_bytes(b"fake")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    monkeypatch.setattr(sys, "argv", ["snark"])
    assert verify_update_permissions() == binary.resolve()


def test_verify_update_permissions_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "missing-snark"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    monkeypatch.setattr(sys, "argv", ["snark"])
    with pytest.raises(OSError, match="not found"):
        verify_update_permissions()


@patch("snark.update.check.download_asset")
@patch("snark.update.check.verify_update_permissions")
@patch("snark.update.check.fetch_release")
def test_cli_update_checks_permissions_before_download(
    mock_fetch: MagicMock,
    mock_verify: MagicMock,
    mock_download: MagicMock,
) -> None:
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(200, "0.2.0"),),
    )
    mock_verify.side_effect = OSError("cannot update: no write permission")
    with (
        patch("snark.update.check.get_version", return_value=V0_1_0),
        patch("snark.update.check.is_frozen", return_value=True),
    ):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "no write permission" in result.stderr
    mock_verify.assert_called_once()
    mock_download.assert_not_called()


@patch("snark.update.check.apply_binary_update")
@patch("snark.update.check.download_asset")
@patch("snark.update.check.verify_update_permissions")
@patch("snark.update.check.fetch_release")
def test_cli_update_replaces_running_executable(
    mock_fetch: MagicMock,
    mock_verify: MagicMock,
    mock_download: MagicMock,
    mock_apply: MagicMock,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "snark"
    binary.write_bytes(b"old")
    staging = tmp_path / "staging"
    staging.write_bytes(b"new")
    mock_fetch.return_value = GitHubRelease(
        tag_name="dev",
        assets=(_asset(200, "0.2.0"),),
    )
    mock_verify.return_value = binary
    mock_download.return_value = staging
    with (
        patch("snark.update.check.get_version", return_value=V0_1_0),
        patch("snark.update.check.is_frozen", return_value=True),
    ):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    mock_verify.assert_called_once()
    mock_download.assert_called_once()
    mock_apply.assert_called_once_with(
        staging,
        version="0.2.0",
        asset_id=200,
    )
