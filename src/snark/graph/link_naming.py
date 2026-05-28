"""Deterministic link naming for pyfits."""

from __future__ import annotations

from pyfits import TargetId

from snark.model import Hardness, PrecedenceEdge, RelationType


def precedes_link_type(relation: RelationType, hardness: Hardness) -> str:
    """Map precedence attributes to registered link type name."""
    return f"precedes_{relation.value}_{hardness.value}"


def display_name(link_type: str, from_ref: str, to_ref: str) -> str:
    """Human-readable link name: ``{link_type}:{from}->{to}``."""
    return f"{link_type}:{from_ref}->{to_ref}"


def wire_target_id(link_type: str, from_ref: str, to_ref: str) -> TargetId:
    """Single-segment opaque id for pyfits ``target_id`` on link create."""
    raw = f"{link_type}--{from_ref}--{to_ref}".replace("/", "--")
    return TargetId.parse(raw)


def precedes_target_id(edge: PrecedenceEdge) -> TargetId:
    """Target id for a precedence edge."""
    lt = precedes_link_type(edge.relation, edge.hardness)
    return wire_target_id(lt, edge.predecessor, edge.successor)
