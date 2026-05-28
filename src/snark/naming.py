"""Kebab-case naming validation and slug derivation."""

from __future__ import annotations

import re

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def validate_kebab(name: str) -> None:
    """Raise ValueError if ``name`` is not lowercase kebab-case."""
    if not KEBAB_CASE_RE.fullmatch(name):
        msg = (
            f"name {name!r} must be lowercase kebab-case "
            "(e.g. billing-redesign)"
        )
        raise ValueError(msg)


def slugify(text: str) -> str:
    """Derive a kebab-case slug from arbitrary heading text."""
    lowered = text.strip().lower()
    slug = _SLUG_CLEAN_RE.sub("-", lowered).strip("-")
    if not slug:
        msg = f"cannot derive slug from {text!r}"
        raise ValueError(msg)
    validate_kebab(slug)
    return slug


def normalize_entity_name(raw: str) -> str:
    """Strip optional ``.md`` suffix and validate kebab-case name."""
    name = raw.removesuffix(".md")
    validate_kebab(name)
    return name
