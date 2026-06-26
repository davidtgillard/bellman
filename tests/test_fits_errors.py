"""Tests for libfits duplicate-error helpers."""

from __future__ import annotations

from pyfits import Id
from pyfits.errors import FitsError, FitsStatus
from pyfits.result import Err, Ok

from bellman.graph.fits_errors import (
    ignore_duplicate_instance,
    ignore_if_already_exists,
    ignore_nothing_to_remove,
    is_already_exists,
    is_nothing_to_remove,
)


def test_is_already_exists_by_code() -> None:
    err = FitsError("node type 'req' already registered", code="DuplicateNodeType")
    assert is_already_exists(err)


def test_is_already_exists_by_status() -> None:
    err = FitsError("duplicate", status=FitsStatus.ERR_INTERNAL)
    assert not is_already_exists(err)
    legacy = FitsError("duplicate", status=-14)  # type: ignore[arg-type]
    assert is_already_exists(legacy)


def test_ignore_if_already_exists() -> None:
    err = FitsError("link type already registered", code="DuplicateLinkType")
    result = ignore_if_already_exists(Err(err))
    assert isinstance(result, Ok)


def test_ignore_duplicate_instance() -> None:
    err = FitsError("instance id 'x' already registered", code="DuplicateInstanceId")
    node_id = Id("x")
    result = ignore_duplicate_instance(Err(err), node_id=node_id)
    assert isinstance(result, Ok)
    assert result.ok_value == node_id


def test_is_nothing_to_remove() -> None:
    err = FitsError("internal error", code="NothingToRemove")
    assert is_nothing_to_remove(err)
    assert not is_nothing_to_remove(FitsError("boom", code="OutOfMemory"))


def test_ignore_nothing_to_remove() -> None:
    err = FitsError("internal error", code="NothingToRemove")
    result = ignore_nothing_to_remove(Err(err))
    assert isinstance(result, Ok)
