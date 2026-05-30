"""Parse goal markdown files."""

from __future__ import annotations

from pathlib import Path

from snark.model import Goal
from snark.naming import normalize_entity_name
from snark.parse._sections import split_sections


def parse_goal(path: Path) -> Goal:
    """Parse a goal file."""
    text = path.read_text(encoding="utf-8")
    name = normalize_entity_name(path.stem)
    title, sections = split_sections(text)
    if title is None or not title.strip():
        msg = f"missing top-level header (# heading) in {path}"
        raise ValueError(msg)
    body_parts: list[str] = []
    for line in text.splitlines():
        if line.startswith("# "):
            continue
        body_parts.append(line)
    description = "\n".join(body_parts).strip()
    if sections:
        description = sections[0].body if sections[0].level > 1 else description
    return Goal(
        name=name,
        title=title,
        path=str(path),
        description=description,
    )
