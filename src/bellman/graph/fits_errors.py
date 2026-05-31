"""Helpers for libfits duplicate / already-exists errors during idempotent sync."""

from __future__ import annotations

from pyfits import Id
from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

# JSON ``error.code`` values for FITS_ERR_ALREADY_EXISTS (libfits 0.4+).
_ALREADY_EXISTS_CODES = frozenset(
    {
        "DuplicateNodeType",
        "DuplicateLinkType",
        "DuplicateInstanceId",
    }
)

# Stable C status when pyfits.FitsStatus has not yet gained ERR_ALREADY_EXISTS.
_ERR_ALREADY_EXISTS = -14


def is_already_exists(error: FitsError) -> bool:
    """Return True when ``error`` reports a duplicate registration in scope."""
    if error.code in _ALREADY_EXISTS_CODES:
        return True
    return error.status is not None and int(error.status) == _ERR_ALREADY_EXISTS


def ignore_if_already_exists(
    result: Result[None, FitsError],
) -> Result[None, FitsError]:
    """Treat duplicate type registration as success for bootstrap sync."""
    if isinstance(result, Err) and is_already_exists(result.err_value):
        return Ok(None)
    return result


def ignore_duplicate_instance(
    result: Result[Id, FitsError],
    *,
    node_id: Id,
) -> Result[Id, FitsError]:
    """Treat duplicate opaque node ids as success when ensuring graph nodes."""
    if isinstance(result, Err) and is_already_exists(result.err_value):
        return Ok(node_id)
    return result


def ignore_duplicate_link(
    result: Result[Id, FitsError],
    *,
    link_id: Id,
) -> Result[Id, FitsError]:
    """Treat duplicate opaque link ids as success when ensuring graph links."""
    if isinstance(result, Err) and is_already_exists(result.err_value):
        return Ok(link_id)
    return result
