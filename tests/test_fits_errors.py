"""Tests for libfits duplicate-error helpers."""

from __future__ import annotations

from pyfits import Id
from pyfits.errors import FitsError, FitsStatus
from pyfits.result import Err, Ok

from snark.graph.fits_errors import (
    ignore_duplicate_instance,
    ignore_if_already_exists,
    is_already_exists,
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
