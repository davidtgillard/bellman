"""Deterministic link naming for pyfits."""

from __future__ import annotations

from pyfits import InstanceName

from bellman.model import Hardness, PrecedenceEdge, RelationType


def precedes_link_type(relation: RelationType, hardness: Hardness) -> str:
    """Map precedence attributes to registered link type name."""
    return f"precedes_{relation.value}_{hardness.value}"


def display_name(link_type: str, from_ref: str, to_ref: str) -> str:
    """Human-readable link name: ``{link_type}:{from}->{to}``."""
    return f"{link_type}:{from_ref}->{to_ref}"


def wire_link_name(link_type: str, from_ref: str, to_ref: str) -> InstanceName:
    """Deterministic human link name for pyfits ``name`` on link create."""
    raw = f"{link_type}--{from_ref}--{to_ref}".replace("/", "--")
    return InstanceName(raw)


def precedes_link_name(edge: PrecedenceEdge) -> InstanceName:
    """Link name for a precedence edge."""
    lt = precedes_link_type(edge.relation, edge.hardness)
    return wire_link_name(lt, edge.predecessor, edge.successor)
