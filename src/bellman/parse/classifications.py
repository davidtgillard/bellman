"""Parse attribute assignments (``## Classifications`` and work-package YAML).

Markdown grammar, one assignment per bullet::

    - <name>[@<x.y>]: <value> [<key>: <value>, ...]

``name`` is a kebab-case attribute name, ``@x.y`` optionally pins the
attribute contract version the assignment was written against, ``value`` is a
token, and the optional bracketed payload is flat ``key: value`` data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from bellman.model import (
    AttributeAssignment,
    AttributeScalar,
    AttributeValue,
    AttributeVersion,
)
from bellman.naming import KEBAB_CASE_RE

__all__ = [
    "CLASSIFICATIONS_TITLE",
    "parse_classifications_section",
    "parse_classifications_yaml",
    "parse_version",
    "split_classifications_section",
    "split_name_and_pin",
]

CLASSIFICATIONS_TITLE = "Classifications"
"""Level-2 heading that holds an entity's attribute assignments."""

_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_NAME_PIN_RE = re.compile(r"^(?P<name>[^@\s]+)(?:@(?P<version>\S+))?$")
_TOKEN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_LINE_RE = re.compile(
    r"^\s*-\s+(?P<head>[^\s:]+)\s*:\s*(?P<value>" + _TOKEN + r")"
    r"\s*(?:\[(?P<payload>[^\]]*)\])?\s*$"
)
_PAYLOAD_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
_FLOAT_RE = re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+([eE][+-]?[0-9]+)?$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_version(text: str) -> AttributeVersion:
    """Parse an ``x.y`` attribute version.

    Args:
        text: Version text such as ``"1.2"``.

    Returns:
        ``(major, minor)`` integers.

    Raises:
        ValueError: When ``text`` is not ``x.y`` with non-negative integers
            and no leading zeros.
    """
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        msg = f"invalid version {text!r}; expected x.y (for example 1.0)"
        raise ValueError(msg)
    return int(match.group(1)), int(match.group(2))


def split_name_and_pin(head: str) -> tuple[str, AttributeVersion | None]:
    """Split ``name`` or ``name@x.y`` into the attribute name and pin.

    Args:
        head: Assignment key such as ``program`` or ``program@1.2``.

    Returns:
        The attribute name and the pinned version (``None`` when unpinned).

    Raises:
        ValueError: When the name is not kebab-case or the pin is not ``x.y``.
    """
    match = _NAME_PIN_RE.fullmatch(head)
    if match is None:
        msg = f"invalid attribute reference {head!r}"
        raise ValueError(msg)
    name = match.group("name")
    if not KEBAB_CASE_RE.fullmatch(name):
        msg = f"attribute name {name!r} must be lowercase kebab-case"
        raise ValueError(msg)
    raw_version = match.group("version")
    if raw_version is None:
        return name, None
    return name, parse_version(raw_version)


def _parse_scalar(text: str) -> AttributeScalar:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    if _INT_RE.fullmatch(stripped):
        return int(stripped)
    if _FLOAT_RE.fullmatch(stripped):
        return float(stripped)
    return stripped


def _split_payload_items(payload: str) -> list[str]:
    """Split ``a: 1, b: "x, y"`` on commas that are outside double quotes."""
    items: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in payload:
        if ch == '"':
            in_quotes = not in_quotes
        if ch == "," and not in_quotes:
            items.append("".join(current))
            current = []
            continue
        current.append(ch)
    items.append("".join(current))
    return [item for item in items if item.strip()]


def _parse_payload(payload: str, line_no: int, line: str) -> dict[str, AttributeScalar]:
    data: dict[str, AttributeScalar] = {}
    for item in _split_payload_items(payload):
        key, sep, raw = item.partition(":")
        key = key.strip()
        if not sep or not _PAYLOAD_KEY_RE.fullmatch(key) or not raw.strip():
            msg = (
                f"invalid classification payload at line {line_no}: {line!r}; "
                "expected '[key: value, ...]'"
            )
            raise ValueError(msg)
        if key in data:
            msg = (
                f"duplicate classification payload key {key!r} "
                f"at line {line_no}: {line!r}"
            )
            raise ValueError(msg)
        data[key] = _parse_scalar(raw)
    return data


def parse_classifications_section(body: str) -> tuple[AttributeAssignment, ...]:
    """Parse the bullets of a ``## Classifications`` section.

    Args:
        body: Markdown body of the section.

    Returns:
        Assignments in document order.

    Raises:
        ValueError: When a non-empty, non-comment line does not match
            ``- <name>[@<x.y>]: <value> [<key>: <value>, ...]``.
    """
    assignments: list[AttributeAssignment] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            msg = (
                f"invalid classification syntax at line {line_no}: {line!r}; "
                "expected '- <name>[@x.y]: <value> [key: value, ...]'"
            )
            raise ValueError(msg)
        try:
            name, pin = split_name_and_pin(match.group("head"))
        except ValueError as exc:
            msg = f"invalid classification at line {line_no}: {line!r}; {exc}"
            raise ValueError(msg) from exc
        raw_payload = match.group("payload")
        payload = (
            _parse_payload(raw_payload, line_no, line)
            if raw_payload is not None
            else {}
        )
        assignments.append(
            AttributeAssignment(
                name=name,
                value=match.group("value"),
                payload=payload,
                pinned_version=pin,
            )
        )
    return tuple(assignments)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def _flat_scalars(raw: Mapping[Any, Any]) -> dict[str, AttributeScalar] | None:
    out: dict[str, AttributeScalar] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _is_scalar(value):
            return None
        out[key] = value
    return out


def _yaml_assignment(
    name: str,
    pin: AttributeVersion | None,
    entry: Any,
    where: str,
) -> AttributeAssignment:
    if isinstance(entry, dict):
        if "value" not in entry:
            msg = f"classification {name!r} entry missing 'value' {where}"
            raise ValueError(msg)
        rest = {k: v for k, v in entry.items() if k != "value"}
        payload = _flat_scalars(rest)
        if payload is None:
            msg = f"classification {name!r} payload must be flat scalars {where}"
            raise ValueError(msg)
        raw_value = entry["value"]
        value: AttributeValue
        if isinstance(raw_value, dict):
            flat = _flat_scalars(raw_value)
            if flat is None:
                msg = f"classification {name!r} value must be flat scalars {where}"
                raise ValueError(msg)
            value = flat
        elif _is_scalar(raw_value):
            value = raw_value
        else:
            msg = f"classification {name!r} has an invalid value {where}"
            raise ValueError(msg)
        return AttributeAssignment(
            name=name, value=value, payload=payload, pinned_version=pin
        )
    if _is_scalar(entry):
        return AttributeAssignment(name=name, value=entry, pinned_version=pin)
    msg = f"classification {name!r} has an invalid value {where}"
    raise ValueError(msg)


def parse_classifications_yaml(
    raw: Any,
    *,
    path: str,
    owner: str,
) -> tuple[AttributeAssignment, ...]:
    """Parse a work package ``classifications`` mapping.

    Each key is ``name`` or ``name@x.y``. Each value is a scalar, a mapping with
    a ``value`` key (other keys form the payload), or a list of either.

    Args:
        raw: The decoded YAML value of ``classifications`` (``None`` allowed).
        path: File path used in error messages.
        owner: Work package slug used in error messages.

    Returns:
        Assignments in mapping order.

    Raises:
        ValueError: When the structure is invalid.
    """
    if raw is None:
        return ()
    where = f"for work package {owner!r} in {path}"
    if not isinstance(raw, dict):
        msg = f"classifications must be a mapping {where}"
        raise ValueError(msg)
    assignments: list[AttributeAssignment] = []
    for key, item in raw.items():
        try:
            name, pin = split_name_and_pin(str(key))
        except ValueError as exc:
            msg = f"invalid classification {key!r} {where}: {exc}"
            raise ValueError(msg) from exc
        entries = item if isinstance(item, list) else [item]
        for entry in entries:
            assignments.append(_yaml_assignment(name, pin, entry, where))
    return tuple(assignments)


def split_classifications_section(text: str) -> tuple[str, str | None]:
    """Remove the ``## Classifications`` section from markdown text.

    Args:
        text: Full markdown document.

    Returns:
        The document without the section, and the section body (``None`` when
        absent). The section runs until the next heading of level 1 or 2.
    """
    lines = text.splitlines()
    kept: list[str] = []
    body: list[str] = []
    in_section = False
    found = False
    for line in lines:
        match = _HEADING_RE.match(line)
        if match is not None:
            level = len(match.group(1))
            if level == 2 and match.group(2).strip() == CLASSIFICATIONS_TITLE:
                in_section = True
                found = True
                continue
            if in_section and level <= 2:
                in_section = False
        if in_section:
            body.append(line)
        else:
            kept.append(line)
    if not found:
        return text, None
    return "\n".join(kept) + "\n", "\n".join(body).strip()
