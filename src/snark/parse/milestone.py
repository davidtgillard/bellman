"""Parse milestone markdown files."""

from __future__ import annotations

from pathlib import Path

from snark.model import Milestone
from snark.naming import normalize_entity_name
from snark.parse._sections import section_by_title, split_sections


def parse_milestone(path: Path) -> Milestone:
    """Parse a milestone file."""
    text = path.read_text(encoding="utf-8")
    name = normalize_entity_name(path.stem)
    title, sections = split_sections(text)
    if title is None:
        msg = f"missing title in {path}"
        raise ValueError(msg)
    date_sec = section_by_title(sections, "Date")
    if date_sec is None:
        msg = f"missing ## Date in {path}"
        raise ValueError(msg)
    date = date_sec.body.strip().splitlines()[0].strip()
    desc_sec = section_by_title(sections, "Description")
    description = desc_sec.body if desc_sec is not None else ""
    return Milestone(
        name=name,
        title=title,
        path=str(path),
        date=date,
        description=description.strip(),
    )
