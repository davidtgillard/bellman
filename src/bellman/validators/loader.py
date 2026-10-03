"""Load repo-local custom validators."""

from __future__ import annotations

from bellman.naming import KEBAB_CASE_RE
from bellman.plugin.discover import PluginSpec
from bellman.plugin.loader import PluginLoadError, import_plugin_module
from bellman.validators.protocol import BellmanValidator

__all__ = ["VALIDATOR_EXPORT", "ValidatorLoadError", "load_validator"]

VALIDATOR_EXPORT = "VALIDATOR"
"""Module attribute a validator must export."""


class ValidatorLoadError(Exception):
    """Failure loading a validator module.

    Attributes:
        message: Human-readable reason.
        path: Path of the offending file or directory, when known.
    """

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path


def load_validator(spec: PluginSpec) -> BellmanValidator:
    """Import and check a validator module.

    Args:
        spec: Discovered validator directory.

    Returns:
        The validated :class:`BellmanValidator`.

    Raises:
        ValidatorLoadError: When import fails, ``VALIDATOR`` is missing or not
            a :class:`BellmanValidator`, the name does not match the directory,
            or ``attributes`` is not a non-empty tuple or list of kebab-case
            attribute names.
    """
    path = str(spec.path)
    try:
        module = import_plugin_module(spec)
    except PluginLoadError as exc:
        raise ValidatorLoadError(exc.message, path=exc.path or path) from exc

    validator = getattr(module, VALIDATOR_EXPORT, None)
    if not isinstance(validator, BellmanValidator):
        msg = f"module must define {VALIDATOR_EXPORT} as BellmanValidator"
        raise ValidatorLoadError(msg, path=path)
    if validator.name != spec.name:
        msg = (
            f"validator name {validator.name!r} does not match directory {spec.name!r}"
        )
        raise ValidatorLoadError(msg, path=path)
    if not KEBAB_CASE_RE.fullmatch(validator.name):
        msg = f"validator name {validator.name!r} must be lowercase kebab-case"
        raise ValidatorLoadError(msg, path=path)

    attributes = validator.attributes
    if (
        not isinstance(attributes, tuple | list)
        or not attributes
        or not all(
            isinstance(a, str) and KEBAB_CASE_RE.fullmatch(a) for a in attributes
        )
    ):
        msg = "attributes must be a non-empty tuple of kebab-case attribute names"
        raise ValidatorLoadError(msg, path=path)
    if not callable(validator.run):
        msg = "run must be callable"
        raise ValidatorLoadError(msg, path=path)
    return validator
