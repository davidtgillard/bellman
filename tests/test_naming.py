"""Tests for naming helpers."""

from __future__ import annotations

import pytest

from snark.naming import normalize_entity_name, slugify, validate_kebab


def test_validate_kebab_accepts_valid() -> None:
    validate_kebab("billing-redesign")
    validate_kebab("a")


def test_validate_kebab_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="kebab-case"):
        validate_kebab("Billing-Redesign")
    with pytest.raises(ValueError, match="kebab-case"):
        validate_kebab("has_underscore")


def test_slugify() -> None:
    assert slugify("WP Invoicing") == "wp-invoicing"


def test_normalize_entity_name() -> None:
    assert normalize_entity_name("foo.md") == "foo"
