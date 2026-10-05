"""Repo-local custom validators for roadmap rules a JSON Schema cannot express.

A validator lives in ``validator/{name}/`` at the roadmap root and exports a
``VALIDATOR`` object::

    from bellman.errors import BellmanError
    from bellman.validators import BellmanValidator, ValidationContext


    def check(ctx: ValidationContext):
        for ref in ctx.entities(kind="project"):
            is_p0 = any(a.value == "P0" for a in ref.assignments("priority"))
            if is_p0 and not ref.assignments("program"):
                yield BellmanError(ref.path, "P0 projects must belong to a program")


    VALIDATOR = BellmanValidator(
        name="p0-needs-program",
        summary="P0 projects must belong to a program",
        attributes=("priority", "program"),
        run=check,
    )

The standalone binary runs validators that import only the standard library
and ``bellman``. A load failure there is a warning (an error with
``--require-validators``); a source install reports load failures as errors.
"""

from bellman.validators.discover import VALIDATOR_DIR, discover_validators
from bellman.validators.loader import (
    VALIDATOR_EXPORT,
    ValidatorLoadError,
    load_validator,
)
from bellman.validators.protocol import (
    BellmanValidator,
    ValidationContext,
    ValidatorRun,
)
from bellman.validators.runner import validate_roadmap_full

__all__ = [
    "VALIDATOR_DIR",
    "VALIDATOR_EXPORT",
    "BellmanValidator",
    "ValidationContext",
    "ValidatorLoadError",
    "ValidatorRun",
    "discover_validators",
    "load_validator",
    "validate_roadmap_full",
]
