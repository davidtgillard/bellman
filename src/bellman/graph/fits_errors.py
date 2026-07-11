"""Helpers for libfits duplicate / already-exists errors during idempotent sync."""

from __future__ import annotations

from pyfits import CreatedObject, Id
from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

# JSON ``error.code`` values for FITS_ERR_ALREADY_EXISTS (libfits 0.5+).
_ALREADY_EXISTS_CODES = frozenset(
    {
        "DuplicateNodeType",
        "DuplicateLinkType",
        "DuplicateInstanceName",
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
    result: Result[CreatedObject, FitsError],
    *,
    logical_name: str,
    guid: Id | None = None,
) -> Result[CreatedObject, FitsError]:
    """Treat duplicate instance names as success when ensuring graph nodes."""
    if isinstance(result, Err) and is_already_exists(result.err_value):
        if guid is not None:
            return Ok(CreatedObject(guid=guid, name=logical_name))
        return Err(result.err_value)
    return result


def ignore_duplicate_link(
    result: Result[CreatedObject, FitsError],
    *,
    link_name: str,
    guid: Id | None = None,
) -> Result[CreatedObject, FitsError]:
    """Treat duplicate link names as success when ensuring graph links."""
    if isinstance(result, Err) and is_already_exists(result.err_value):
        if guid is not None:
            return Ok(CreatedObject(guid=guid, name=link_name))
        return Err(result.err_value)
    return result


def is_nothing_to_remove(error: FitsError) -> bool:
    """Return True when libfits has a registry entry but no on-disk object to remove."""
    return error.code == "NothingToRemove"


def ignore_nothing_to_remove(
    result: Result[None, FitsError],
) -> Result[None, FitsError]:
    """Treat missing on-disk instances as success when pruning stale graph objects."""
    if isinstance(result, Err) and is_nothing_to_remove(result.err_value):
        return Ok(None)
    return result
