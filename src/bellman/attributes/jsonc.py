"""Minimal JSONC (JSON with comments) parsing."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["loads_jsonc", "strip_jsonc"]


def _strip_comments(text: str) -> str:
    """Replace ``//`` and ``/* */`` comments outside strings with whitespace.

    Newlines are preserved so decode errors report the original line numbers.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                msg = "unterminated block comment"
                raise ValueError(msg)
            out.extend("\n" if c == "\n" else " " for c in text[i : end + 2])
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove commas that directly precede ``}`` or ``]`` outside strings."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                out.append(" ")
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_jsonc(text: str) -> str:
    """Convert JSONC text to plain JSON text.

    Comments (``//`` and ``/* */``) and trailing commas are removed. Content
    inside string literals, including ``//``, is left unchanged. Line numbers
    are preserved.

    Args:
        text: JSONC source.

    Returns:
        JSON text suitable for :func:`json.loads`.

    Raises:
        ValueError: When a block comment is not terminated.
    """
    return _strip_trailing_commas(_strip_comments(text))


def loads_jsonc(text: str) -> Any:
    """Parse JSONC text.

    Args:
        text: JSONC source.

    Returns:
        The decoded JSON value.

    Raises:
        ValueError: When the text is not valid JSONC (this includes
            :class:`json.JSONDecodeError`).
    """
    return json.loads(strip_jsonc(text))
