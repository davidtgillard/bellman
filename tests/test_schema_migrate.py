"""Unit tests for registry schema migration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pyfits.result import Err, Ok

from bellman.graph.registry import KIND_TYPE
from bellman.graph.schema_migrate import (
    is_kind_root_name,
    migrate_registry_schema,
    registry_needs_schema_migration,
)


def _write_registry(root: Path, data: dict) -> Path:
    fits = root / ".fits"
    fits.mkdir(parents=True, exist_ok=True)
    path = fits / "registry.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def test_needs_migration_missing_file(tmp_path: Path) -> None:
    assert registry_needs_schema_migration(tmp_path) is False
    assert isinstance(migrate_registry_schema(tmp_path), Ok)


def test_needs_migration_invalid_json(tmp_path: Path) -> None:
    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text("{not-json", encoding="utf-8")
    assert registry_needs_schema_migration(tmp_path) is False


def test_needs_migration_node_types_not_list(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"node_types": {"goal": True}})
    assert registry_needs_schema_migration(tmp_path) is False


def test_needs_migration_skips_non_dict_entries(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"node_types": ["goal", {"type": "goal"}]})
    assert registry_needs_schema_migration(tmp_path) is True


def test_needs_migration_nested_goal_returns_false(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "node_types": [
                {"type": KIND_TYPE},
                {"type": "goal", "container_node": KIND_TYPE},
            ]
        },
    )
    assert registry_needs_schema_migration(tmp_path) is False


def test_needs_migration_legacy_goal_without_kind(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"node_types": [{"type": "goal"}]})
    assert registry_needs_schema_migration(tmp_path) is True


def test_migrate_noop_when_already_nested(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "node_types": [
                {"type": KIND_TYPE},
                {"type": "goal", "container_node": KIND_TYPE},
            ]
        },
    )
    assert isinstance(migrate_registry_schema(tmp_path), Ok)


def test_migrate_strips_legacy_and_resets_links(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {
            "node_types": [
                {"type": "goal"},
                {"type": "initiative"},
                "skip-me",
                {"type": "custom_keep"},
            ],
            "instances": [
                {"type": "goal", "name": "g1"},
                {"kind": "link", "name": "l1"},
                "skip",
                {"type": "custom", "name": "keep"},
            ],
            "link_types": [
                {"link_type": "parent_of"},
                {"link_type": "precedes_FS_Mandatory"},
                {"link_type": "custom_edge"},
                "skip",
            ],
            "nested_link_types": [{"x": 1}],
            "nested_scopes": {"goal": {}},
        },
    )
    links = tmp_path / "links"
    links.mkdir()
    links_path = links / "links.jsonc"
    links_path.write_text('{"links":[{"id":"old"}]}\n', encoding="utf-8")

    result = migrate_registry_schema(tmp_path)
    assert isinstance(result, Ok)

    data = json.loads(
        (tmp_path / ".fits" / "registry.json").read_text(encoding="utf-8")
    )
    assert data["node_types"] == [{"type": "custom_keep"}]
    assert data["instances"] == [{"type": "custom", "name": "keep"}]
    assert data["link_types"] == [{"link_type": "custom_edge"}]
    assert data["nested_link_types"] == []
    assert data["nested_scopes"] == {}

    reset = links_path.read_text(encoding="utf-8")
    assert '"links": []' in reset
    assert "fits-links-v1" in reset


def test_migrate_read_failure_returns_err(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, {"node_types": [{"type": "goal"}]})

    def _read(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        if self == path:
            raise OSError("boom")
        return Path.read_text(self, encoding=encoding, errors=errors)

    with (
        patch(
            "bellman.graph.schema_migrate.registry_needs_schema_migration",
            return_value=True,
        ),
        patch.object(Path, "read_text", _read),
    ):
        result = migrate_registry_schema(tmp_path)
    assert isinstance(result, Err)
    assert result.err_value.code == "schema_migration_failed"


def test_migrate_write_registry_failure(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, {"node_types": [{"type": "goal"}]})
    original = Path.write_text

    def _write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self == path:
            raise OSError("denied")
        return original(self, data, encoding=encoding, errors=errors, newline=newline)

    with patch.object(Path, "write_text", _write):
        result = migrate_registry_schema(tmp_path)
    assert isinstance(result, Err)
    assert result.err_value.code == "schema_migration_failed"


def test_migrate_write_links_failure(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"node_types": [{"type": "goal"}]})
    links = tmp_path / "links"
    links.mkdir()
    links_path = links / "links.jsonc"
    links_path.write_text("{}\n", encoding="utf-8")
    original = Path.write_text

    def _write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self == links_path:
            raise OSError("links denied")
        return original(self, data, encoding=encoding, errors=errors, newline=newline)

    with patch.object(Path, "write_text", _write):
        result = migrate_registry_schema(tmp_path)
    assert isinstance(result, Err)
    assert result.err_value.code == "schema_migration_failed"


def test_is_kind_root_name() -> None:
    assert is_kind_root_name("goal") is True
    assert is_kind_root_name("wp") is False
