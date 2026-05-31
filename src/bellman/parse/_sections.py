"""Shared markdown section utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Section:
    """A markdown section with heading level and body."""

    level: int
    title: str
    body: str
    line: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_sections(text: str) -> tuple[str | None, list[Section]]:
    """Split markdown into title (first H1) and sections."""
    lines = text.splitlines()
    title: str | None = None
    sections: list[Section] = []
    current: Section | None = None
    body_lines: list[str] = []

    for lineno, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match is None:
            if current is not None:
                body_lines.append(line)
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        if level == 1 and title is None:
            title = heading
            continue
        if current is not None:
            current = Section(
                level=current.level,
                title=current.title,
                body="\n".join(body_lines).strip(),
                line=current.line,
            )
            sections.append(current)
            body_lines = []
        current = Section(level=level, title=heading, body="", line=lineno)

    if current is not None:
        sections.append(
            Section(
                level=current.level,
                title=current.title,
                body="\n".join(body_lines).strip(),
                line=current.line,
            )
        )
    return title, sections


def section_by_title(sections: list[Section], title: str) -> Section | None:
    """Return first level-2 section with exact title (case-sensitive)."""
    for sec in sections:
        if sec.level == 2 and sec.title == title:
            return sec
    return None


def subsections(parent: Section, all_sections: list[Section]) -> list[Section]:
    """Return direct child sections under ``parent`` in document order."""
    try:
        start = all_sections.index(parent)
    except ValueError:
        return []
    children: list[Section] = []
    for sec in all_sections[start + 1 :]:
        if sec.level <= parent.level:
            break
        if sec.level == parent.level + 1:
            children.append(sec)
    return children
