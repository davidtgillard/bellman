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

_FROZEN_LOAD_HINT = "keep validators to the Python standard library and bellman"


def _frozen_load_skip(label: str, detail: str) -> str:
    return (
        f"{label} skipped: could not load in the standalone binary "
        f"({detail}); {_FROZEN_LOAD_HINT}"
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
    is reported as a warning naming those attributes). Frozen (standalone
    binary) builds try the same import. A load failure there skips that one
    validator (a warning, or an error when ``require_validators`` is set) so a
    missing third-party module does not hide the rest. A source install still
    reports load failures as errors.

    Args:
        root: Roadmap root directory.
        roadmap: Loaded roadmap.
        require_validators: When true, a validator that cannot be loaded in a
            frozen build is an error instead of a warning.

    Returns:
        Built-in findings followed by validator findings. Load failures in a
        source install, and exceptions raised inside a validator, are reported
        as errors naming the validator.
    """
    base = validate_roadmap(roadmap)
    specs = discover_validators(root)
    if not specs:
        return base

    errors: list[BellmanError] = []
    warnings: list[BellmanWarning] = []

    failed = check_attributes_detailed(roadmap).failed_attributes
    context = ValidationContext(roadmap=roadmap, root=root)
    catalog = roadmap.attributes

    for spec in specs:
        label = f"validator {spec.name!r}"
        try:
            validator = load_validator(spec)
        except ValidatorLoadError as exc:
            path = exc.path or str(spec.path)
            if is_frozen():
                message = _frozen_load_skip(label, exc.message)
                finding_error = BellmanError(path, message)
                finding_warning = BellmanWarning(path, message)
                if require_validators:
                    errors.append(finding_error)
                else:
                    warnings.append(finding_warning)
            else:
                errors.append(BellmanError(path, f"{label}: {exc.message}"))
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
