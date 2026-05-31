"""Parse work-packages.md."""

from __future__ import annotations

import re
from pathlib import Path

from snark.model import (
    UNKNOWN_ESTIMATE,
    Estimate,
    PrecedenceEdge,
    ThreePointEstimate,
    WorkPackage,
)
from snark.naming import slugify, validate_kebab
from snark.parse._sections import Section, split_sections, subsections
from snark.parse.dependencies import parse_dependencies_section

_ESTIMATE_RE = re.compile(
    r"^\s*-\s+(optimistic|most likely|pessimistic|unit):\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _invalid_estimate_msg(slug: str, path: str) -> str:
    return (
        f"estimate must be unknown or a complete 3-point estimate "
        f"for work package {slug!r} in {path}"
    )


def _parse_estimate(body: str, path: str, slug: str) -> Estimate | None:
    stripped = body.strip()
    if not stripped:
        return None
    if stripped.lower() == "unknown":
        return UNKNOWN_ESTIMATE
    values: dict[str, str] = {}
    matched_any = False
    for line in body.splitlines():
        match = _ESTIMATE_RE.match(line)
        if match is None:
            if line.strip():
                raise ValueError(_invalid_estimate_msg(slug, path))
            continue
        matched_any = True
        key = match.group(1).lower().replace(" ", "_")
        raw = match.group(2).strip()
        if raw.lower() == "unknown":
            msg = (
                f"partial estimate with unknown values is not supported "
                f"for work package {slug!r} in {path}"
            )
            raise ValueError(msg)
        values[key] = raw
    if not matched_any:
        raise ValueError(_invalid_estimate_msg(slug, path))
    required = ("optimistic", "most_likely", "pessimistic", "unit")
    if not all(k in values for k in required):
        msg = f"incomplete estimate for work package {slug!r} in {path}"
        raise ValueError(msg)
    unit = values["unit"].lower()
    if unit not in ("days", "weeks"):
        msg = f"unit must be days or weeks in {path}"
        raise ValueError(msg)
    return ThreePointEstimate(
        optimistic=float(values["optimistic"]),
        most_likely=float(values["most_likely"]),
        pessimistic=float(values["pessimistic"]),
        unit=unit,  # type: ignore[arg-type]
    )


def _section_slug(section: Section) -> str:
    try:
        validate_kebab(section.title)
        return section.title
    except ValueError:
        return slugify(section.title)


def _parse_wp_tree(
    section: Section,
    all_sections: list[Section],
    path: str,
    project_name: str,
) -> WorkPackage:
    slug = _section_slug(section)
    child_headers = subsections(section, all_sections)
    # Description: text before first ### subsection
    description = section.body
    estimate: Estimate | None = None
    dep_edges: tuple[PrecedenceEdge, ...] = ()
    children: list[WorkPackage] = []

    for sub in child_headers:
        lower = sub.title.lower()
        if lower == "estimate":
            estimate = _parse_estimate(sub.body, path, slug)
            description = _strip_subsection(description, sub.title)
        elif lower in ("work packages", "work package"):
            for child_sec in subsections(sub, all_sections):
                if child_sec.level == sub.level + 1:
                    children.append(
                        _parse_wp_tree(child_sec, all_sections, path, project_name)
                    )
        elif lower == "dependencies":
            dep_edges = tuple(
                parse_dependencies_section(
                    sub.body,
                    successor=f"{project_name}/{slug}",
                )
            )
            description = _strip_subsection(description, sub.title)

    return WorkPackage(
        slug=slug,
        description=description.strip(),
        estimate=estimate,
        children=tuple(children),
        dependencies=dep_edges,
    )


def _strip_subsection(body: str, heading: str) -> str:
    marker = f"### {heading}"
    if marker in body:
        return body.split(marker, maxsplit=1)[0]
    return body


def parse_work_packages(path: Path, *, project_name: str) -> list[WorkPackage]:
    """Parse root work packages from work-packages.md."""
    text = path.read_text(encoding="utf-8")
    rel = str(path)
    _title, sections = split_sections(text)
    roots = [s for s in sections if s.level == 2]
    return [_parse_wp_tree(sec, sections, rel, project_name) for sec in roots]
