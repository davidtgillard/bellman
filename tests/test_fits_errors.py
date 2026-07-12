"""Tests for libfits duplicate-error helpers."""

from __future__ import annotations

from pyfits import CreatedObject, Id
from pyfits.errors import FitsError, FitsStatus
from pyfits.result import Err, Ok

from bellman.graph.fits_errors import (
    format_fits_error,
    ignore_duplicate_instance,
    ignore_if_already_exists,
    ignore_nothing_to_remove,
    is_already_exists,
    is_nothing_to_remove,
)


def test_is_already_exists_by_code() -> None:
    err = FitsError("node type 'req' already registered", code="DuplicateNodeType")
    assert is_already_exists(err)


def test_is_already_exists_by_name_code() -> None:
    err = FitsError("duplicate name", code="DuplicateInstanceName")
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
    err = FitsError(
        "instance name 'x' already registered", code="DuplicateInstanceName"
    )
    guid = Id("550e8400-e29b-41d4-a716-446655440000")
    result = ignore_duplicate_instance(Err(err), logical_name="x", guid=guid)
    assert isinstance(result, Ok)
    assert result.ok_value == CreatedObject(guid=guid, name="x")


def test_is_nothing_to_remove() -> None:
    err = FitsError("internal error", code="NothingToRemove")
    assert is_nothing_to_remove(err)
    assert not is_nothing_to_remove(FitsError("boom", code="OutOfMemory"))


def test_ignore_nothing_to_remove() -> None:
    err = FitsError("internal error", code="NothingToRemove")
    result = ignore_nothing_to_remove(Err(err))
    assert isinstance(result, Ok)


def test_format_fits_error_message_only() -> None:
    err = FitsError("boom")
    assert format_fits_error(err) == "boom"


def test_format_fits_error_with_code() -> None:
    err = FitsError("internal error", code="DuplicateNestedNode")
    assert format_fits_error(err) == "internal error (code=DuplicateNestedNode)"


def test_format_fits_error_with_status_when_no_code() -> None:
    err = FitsError("libfits call failed", status=FitsStatus.ERR_INTERNAL)
    assert format_fits_error(err) == "libfits call failed (status=ERR_INTERNAL)"


def test_format_fits_error_prefers_code_over_status() -> None:
    err = FitsError(
        "internal error",
        code="DuplicateNestedNode",
        status=FitsStatus.ERR_INTERNAL,
    )
    assert format_fits_error(err) == "internal error (code=DuplicateNestedNode)"
