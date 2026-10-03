"""Example validator: a P0 project must belong to a program."""

from __future__ import annotations

from collections.abc import Iterator

from bellman.errors import BellmanError
from bellman.validators import BellmanValidator, ValidationContext


def check(ctx: ValidationContext) -> Iterator[BellmanError]:
    """Report P0 projects that have no ``program`` assignment."""
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
