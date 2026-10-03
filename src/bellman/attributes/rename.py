"""Rename an attribute value across its definition and every assignment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from bellman import layout
from bellman.attributes.definition import DEFINITION_SUFFIX
from bellman.attributes.jsonc import loads_jsonc
from bellman.errors import BellmanLayoutError
from bellman.naming import validate_kebab
from bellman.parse.classifications import (
    CLASSIFICATIONS_TITLE,
    parse_classifications_section,
    parse_classifications_yaml,
    split_classifications_section,
    split_name_and_pin,
)

__all__ = ["AttributeRenameResult", "rename_attribute_value"]

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_YAML_SCALAR = r"""(?P<val>"[^"]*"|'[^']*'|[^\s#"'\[\]{},]+)"""
_YAML_TAIL = r"(?P<tail>\s*(?:#.*)?)"
_YAML_CLASSIFICATIONS_RE = re.compile(
    r"^(?P<indent>\s*)classifications\s*:\s*(?:#.*)?$"
)
_YAML_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z][A-Za-z0-9-]*(?:@[^\s:]+)?)\s*:(?P<rest>.*)$"
)
_YAML_INLINE_VALUE_RE = re.compile(r"^\s*" + _YAML_SCALAR + _YAML_TAIL + r"$")
_YAML_LIST_ITEM_RE = re.compile(r"^(?P<pre>\s*-\s+)" + _YAML_SCALAR + _YAML_TAIL + r"$")
_YAML_VALUE_KEY_RE = re.compile(
    r"^(?P<pre>\s*(?:-\s+)?value\s*:\s*)" + _YAML_SCALAR + _YAML_TAIL + r"$"
)


@dataclass(frozen=True, slots=True)
class AttributeRenameResult:
    """Outcome of :func:`rename_attribute_value`.

    Attributes:
        attribute: Attribute name.
        old: Previous value or key.
        new: New value or key.
        definition_path: Rewritten definition file.
        updated_paths: Entity files whose assignments were rewritten.
        assignments: Number of assignments rewritten.
    """

    attribute: str
    old: str
    new: str
    definition_path: Path
    updated_paths: tuple[Path, ...]
    assignments: int


def _read(path: Path) -> str:
    """Read text without translating line endings."""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, content: str) -> None:
    """Write text without translating line endings."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def _skip_insignificant(text: str, index: int) -> int:
    """Return the index of the next character that is not space or comment."""
    n = len(text)
    while index < n:
        ch = text[index]
        if ch in " \t\r\n":
            index += 1
        elif text.startswith("//", index):
            while index < n and text[index] != "\n":
                index += 1
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = n if end == -1 else end + 2
        else:
            break
    return index


def _find_value_token(text: str, old: str) -> tuple[int, int] | None:
    """Locate ``old`` as a ``values`` list item or ``values`` object key.

    Only the top-level ``values`` property is searched, and only its direct
    children, so identical strings elsewhere (schemas, entry data) are ignored.
    """
    n = len(text)
    i = 0
    depth = 0
    values_pending = False
    in_values = False
    container = ""
    while i < n:
        ch = text[i]
        if text.startswith("//", i) or text.startswith("/*", i):
            i = _skip_insignificant(text, i)
            continue
        if ch == '"':
            start = i
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            end = i + 1
            i = end
            value = json.loads(text[start:end])
            after = _skip_insignificant(text, end)
            is_key = after < n and text[after] == ":"
            if depth == 1 and is_key and value == "values":
                values_pending = True
            elif in_values and depth == 2 and value == old:
                if (container == "[" and not is_key) or (container == "{" and is_key):
                    return start, end
            continue
        if ch in "{[":
            depth += 1
            if values_pending and depth == 2:
                in_values = True
                container = ch
                values_pending = False
        elif ch in "}]":
            if in_values and depth == 2:
                in_values = False
            depth -= 1
        i += 1
    return None


def _rewrite_definition(text: str, old: str, new: str) -> str:
    located = _find_value_token(text, old)
    if located is None:
        msg = f"could not locate value {old!r} in the definition text"
        raise BellmanLayoutError(msg)
    start, end = located
    return text[:start] + json.dumps(new) + text[end:]


def _markdown_count(text: str, attribute: str, value: str) -> int:
    _rest, body = split_classifications_section(text)
    if body is None:
        return 0
    return sum(
        1
        for a in parse_classifications_section(body)
        if a.name == attribute and a.value == value
    )


def _rewrite_markdown(text: str, attribute: str, old: str, new: str) -> str:
    line_re = re.compile(
        r"^(?P<pre>\s*-\s+"
        + re.escape(attribute)
        + r"(?:@[^\s:]+)?\s*:\s*)"
        + re.escape(old)
        + r"(?P<post>\s*(?:\[[^\]]*\])?\s*)$"
    )
    in_section = False
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body) :]
        heading = _HEADING_RE.match(body)
        if heading is not None:
            level = len(heading.group(1))
            if level == 2 and heading.group(2).strip() == CLASSIFICATIONS_TITLE:
                in_section = True
                out.append(line)
                continue
            if in_section and level <= 2:
                in_section = False
        if in_section:
            match = line_re.match(body)
            if match is not None:
                body = f"{match.group('pre')}{new}{match.group('post')}"
        out.append(body + eol)
    return "".join(out)


def _walk_packages(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
            out.extend(_walk_packages(item.get("sub_packages")))
    return out


def _yaml_count(text: str, attribute: str, value: str, path: Path) -> int:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"{path}: invalid YAML: {exc}"
        raise BellmanLayoutError(msg) from exc
    if not isinstance(data, dict):
        return 0
    count = 0
    for wp in _walk_packages(data.get("work_packages")):
        try:
            assignments = parse_classifications_yaml(
                wp.get("classifications"), path=str(path), owner=str(wp.get("title"))
            )
        except ValueError as exc:
            raise BellmanLayoutError(str(exc)) from exc
        count += sum(1 for a in assignments if a.name == attribute and a.value == value)
    return count


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def _requote(original: str, new: str) -> str:
    if len(original) >= 2 and original[0] == original[-1] and original[0] in "\"'":
        return f"{original[0]}{new}{original[0]}"
    return new


def _rewrite_work_packages(text: str, attribute: str, old: str, new: str) -> str:
    """Rewrite ``classifications`` block entries line by line (keeps comments)."""
    out: list[str] = []
    block_indent: int | None = None  # indent of the ``classifications:`` key
    key_indent: int | None = None  # indent of attribute keys inside the block
    current: str | None = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body) :]
        stripped = body.strip()
        indent = len(body) - len(body.lstrip())
        if block_indent is not None and stripped and not stripped.startswith("#"):
            if indent <= block_indent:
                block_indent = None
                key_indent = None
                current = None
        if block_indent is None:
            header = _YAML_CLASSIFICATIONS_RE.match(body)
            if header is not None:
                block_indent = len(header.group("indent"))
                key_indent = None
                current = None
            out.append(line)
            continue
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        if key_indent is None:
            key_indent = indent
        key_match = _YAML_KEY_RE.match(body)
        if indent == key_indent and key_match is not None:
            try:
                current, _pin = split_name_and_pin(key_match.group("key"))
            except ValueError:
                current = None
            if current == attribute:
                inline = _YAML_INLINE_VALUE_RE.match(key_match.group("rest"))
                if inline is not None and _unquote(inline.group("val")) == old:
                    head = body[: key_match.start("rest")]
                    value = _requote(inline.group("val"), new)
                    body = f"{head} {value}{inline.group('tail')}"
            out.append(body + eol)
            continue
        if current == attribute and indent >= (key_indent or 0):
            for pattern in (_YAML_LIST_ITEM_RE, _YAML_VALUE_KEY_RE):
                match = pattern.match(body)
                if match is not None and _unquote(match.group("val")) == old:
                    value = _requote(match.group("val"), new)
                    body = f"{match.group('pre')}{value}{match.group('tail')}"
                    break
        out.append(body + eol)
    return "".join(out)


def _entity_files(root: Path) -> tuple[list[Path], list[Path]]:
    markdown: list[Path] = []
    for directory in (layout.INITIATIVES_DIR, layout.MILESTONES_DIR, layout.GOALS_DIR):
        base = root / directory
        if base.is_dir():
            markdown.extend(sorted(base.glob("*.md")))
    yaml_files: list[Path] = []
    projects = root / layout.PROJECTS_DIR
    if projects.is_dir():
        for pdir in sorted(projects.iterdir()):
            if not pdir.is_dir():
                continue
            markdown.extend(sorted(pdir.glob("*.md")))
            wp = pdir / "work-packages.yaml"
            if wp.is_file():
                yaml_files.append(wp)
    return markdown, yaml_files


def rename_attribute_value(
    root: Path,
    attribute: str,
    old: str,
    new: str,
) -> AttributeRenameResult:
    """Rename a plain-set member or keyed value of an attribute.

    Rewrites the value in ``attributes/{attribute}.jsonc`` (leaving comments and
    layout alone) and every assignment of it in markdown ``## Classifications``
    sections and ``work-packages.yaml`` files, including parked project
    folders. Versions and pins are not changed. Nothing is written unless every
    file can be rewritten.

    Args:
        root: Roadmap root directory.
        attribute: Attribute name (kebab-case).
        old: Existing value or key.
        new: New value or key.

    Returns:
        Paths touched and the number of assignments rewritten.

    Raises:
        BellmanLayoutError: When the definition is missing or has no fixed
            values, ``old`` is not defined, ``new`` already exists, a file
            cannot be rewritten safely, or a file has invalid classifications.
        ValueError: When ``attribute`` is not kebab-case or ``old`` / ``new``
            is not a valid token.
    """
    validate_kebab(attribute)
    for label, token in (("old", old), ("new", new)):
        if not _TOKEN_RE.fullmatch(token):
            msg = (
                f"{label} value {token!r} must start with a letter or digit and "
                "contain only letters, digits, '.', '_' or '-'"
            )
            raise ValueError(msg)
    if old == new:
        msg = f"value is already named {new!r}"
        raise BellmanLayoutError(msg)

    definition_path = root / layout.ATTRIBUTES_DIR / f"{attribute}{DEFINITION_SUFFIX}"
    if not definition_path.is_file():
        msg = f"unknown attribute {attribute!r}: {definition_path} not found"
        raise BellmanLayoutError(msg)
    definition_text = _read(definition_path)
    try:
        doc = loads_jsonc(definition_text)
    except ValueError as exc:
        msg = f"{definition_path}: invalid attribute definition: {exc}"
        raise BellmanLayoutError(msg) from exc
    values = doc.get("values") if isinstance(doc, dict) else None
    if not isinstance(values, list | dict):
        msg = f"attribute {attribute!r} has no fixed values to rename"
        raise BellmanLayoutError(msg)
    if old not in values:
        msg = f"{old!r} is not a value of attribute {attribute!r}"
        raise BellmanLayoutError(msg)
    if new in values:
        msg = f"{new!r} is already a value of attribute {attribute!r}"
        raise BellmanLayoutError(msg)

    pending: list[tuple[Path, str]] = [
        (definition_path, _rewrite_definition(definition_text, old, new))
    ]
    updated: list[Path] = []
    total = 0
    markdown, yaml_files = _entity_files(root)
    for path in markdown:
        text = _read(path)
        try:
            before = _markdown_count(text, attribute, old)
        except ValueError as exc:
            raise BellmanLayoutError(f"{path}: {exc}") from exc
        if before == 0:
            continue
        rewritten = _rewrite_markdown(text, attribute, old, new)
        if _markdown_count(rewritten, attribute, old) != 0:
            msg = f"{path}: could not rewrite {attribute}: {old}; edit it by hand"
            raise BellmanLayoutError(msg)
        pending.append((path, rewritten))
        updated.append(path)
        total += before
    for path in yaml_files:
        text = _read(path)
        before = _yaml_count(text, attribute, old, path)
        if before == 0:
            continue
        rewritten = _rewrite_work_packages(text, attribute, old, new)
        if _yaml_count(rewritten, attribute, old, path) != 0:
            msg = f"{path}: could not rewrite {attribute}: {old}; edit it by hand"
            raise BellmanLayoutError(msg)
        pending.append((path, rewritten))
        updated.append(path)
        total += before

    for path, content in pending:
        _write(path, content)
    return AttributeRenameResult(
        attribute=attribute,
        old=old,
        new=new,
        definition_path=definition_path,
        updated_paths=tuple(updated),
        assignments=total,
    )
