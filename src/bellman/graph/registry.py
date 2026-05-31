"""Register bellman node and link types in a pyfits repository."""

from __future__ import annotations

from pyfits import Repo
from pyfits.errors import FitsError
from pyfits.result import Err, Ok, Result

from bellman.graph.fits_errors import ignore_if_already_exists
from bellman.model import Hardness, RelationType


def precedes_link_types() -> list[str]:
    """All registered precedence link type names."""
    types: list[str] = []
    for rel in RelationType:
        for hard in Hardness:
            types.append(f"precedes_{rel.value}_{hardness_suffix(hard)}")
    return types


def hardness_suffix(hard: Hardness) -> str:
    """Wire-safe hardness label for link type names."""
    return hard.value


def bootstrap_registry(repo: Repo) -> Result[None, FitsError]:
    """Register bellman types if not already present."""
    steps: list[Result[None, FitsError]] = [
        repo.register_node_type("work_scope", abstract=True),
        repo.register_node_type("initiative", extends="work_scope"),
        repo.register_node_type("project", extends="work_scope"),
        repo.register_node_type("work_package"),
        repo.register_node_type("milestone"),
        repo.register_node_type("goal"),
        repo.register_link_type("supports", "work_scope", "goal"),
        repo.register_link_type("supports_wp", "work_package", "goal"),
        repo.register_link_type("targets", "work_scope", "milestone"),
        repo.register_link_type("targets_wp", "work_package", "milestone"),
        repo.register_link_type("parent_of", "work_package", "work_package"),
        repo.register_link_type("promoted_from", "project", "initiative"),
    ]
    for rel in RelationType:
        for hard in Hardness:
            lt = f"precedes_{rel.value}_{hardness_suffix(hard)}"
            steps.append(repo.register_link_type(lt, "work_package", "work_package"))
            scope_lt = f"{lt}_scope"
            steps.append(repo.register_link_type(scope_lt, "work_scope", "work_scope"))

    for step in steps:
        normalized = ignore_if_already_exists(step)
        if isinstance(normalized, Err):
            return normalized
    return Ok(None)
