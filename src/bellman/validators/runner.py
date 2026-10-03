"""Run built-in checks and repo-local custom validators together."""

from __future__ import annotations

from pathlib import Path

from bellman.attributes.check import check_attributes_detailed
from bellman.errors import BellmanError, BellmanWarning
from bellman.model import Roadmap
from bellman.update.install import is_frozen
from bellman.validate import ValidationResult, validate_roadmap
from bellman.validators.discover import discover_validators
from bellman.validators.loader import ValidatorLoadError, load_validator
from bellman.validators.protocol import ValidationContext

__all__ = ["validate_roadmap_full"]

_FROZEN_HINT = (
    "the standalone binary cannot load repo Python; "
    "run bellman from a Python install to enable it"
)


def validate_roadmap_full(
    root: Path,
    roadmap: Roadmap,
    *,
    require_validators: bool = False,
) -> ValidationResult:
    """Run built-in validation, then custom validators under ``validator/``.

    Validators run after the built-in checks, and only when those produced no
    error for any attribute the validator lists (a validator held back this way
    is reported as a warning naming those attributes). In a frozen (standalone
    binary) build validators are not imported; each one is reported as skipped.

    Args:
        root: Roadmap root directory.
        roadmap: Loaded roadmap.
        require_validators: When true, a validator skipped because the build is
            frozen is an error instead of a warning.

    Returns:
        Built-in findings followed by validator findings. Load failures and
        exceptions raised inside a validator are reported as errors naming the
        validator.
    """
    base = validate_roadmap(roadmap)
    specs = discover_validators(root)
    if not specs:
        return base

    errors: list[BellmanError] = []
    warnings: list[BellmanWarning] = []

    if is_frozen():
        for spec in specs:
            message = f"validator {spec.name!r} skipped: {_FROZEN_HINT}"
            if require_validators:
                errors.append(BellmanError(str(spec.path), message))
            else:
                warnings.append(BellmanWarning(str(spec.path), message))
        return ValidationResult(
            errors=base.errors + tuple(errors),
            warnings=base.warnings + tuple(warnings),
        )

    failed = check_attributes_detailed(roadmap).failed_attributes
    context = ValidationContext(roadmap=roadmap, root=root)
    catalog = roadmap.attributes

    for spec in specs:
        label = f"validator {spec.name!r}"
        try:
            validator = load_validator(spec)
        except ValidatorLoadError as exc:
            errors.append(
                BellmanError(exc.path or str(spec.path), f"{label}: {exc.message}")
            )
            continue

        unknown = [
            a
            for a in validator.attributes
            if a not in catalog and a not in catalog.invalid_names
        ]
        if unknown:
            errors.append(
                BellmanError(
                    str(spec.path),
                    f"{label} reads unknown attribute(s): {', '.join(unknown)}",
                )
            )
            continue
        blocked = sorted(a for a in validator.attributes if a in failed)
        if blocked:
            warnings.append(
                BellmanWarning(
                    str(spec.path),
                    f"{label} skipped: fix the errors for attribute(s) "
                    f"{', '.join(blocked)} first",
                )
            )
            continue

        try:
            findings = list(validator.run(context))
        except Exception as exc:  # noqa: BLE001 - validator code is untrusted
            errors.append(
                BellmanError(
                    str(spec.path),
                    f"{label} raised {type(exc).__name__}: {exc}",
                )
            )
            continue
        for finding in findings:
            if isinstance(finding, BellmanError):
                errors.append(finding)
            elif isinstance(finding, BellmanWarning):
                warnings.append(finding)
            else:
                errors.append(
                    BellmanError(
                        str(spec.path),
                        f"{label} returned {type(finding).__name__}; "
                        "expected BellmanError or BellmanWarning",
                    )
                )

    return ValidationResult(
        errors=base.errors + tuple(errors),
        warnings=base.warnings + tuple(warnings),
    )
