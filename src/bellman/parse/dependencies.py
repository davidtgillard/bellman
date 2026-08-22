"""Parse ## Dependencies sections.

Each bullet names a **predecessor** of the entity that owns the section
(successor-owned). There is no ``after:`` / ``before:`` keyword.
"""

from __future__ import annotations

import re

from bellman.model import Hardness, PrecedenceEdge, RelationType

_DEPENDENCY_RE = re.compile(
    r"^\s*-\s+(?P<predecessor>\S+)\s+"
    r"\[(?P<relation>FF|FS|SF|SS),\s*(?P<hardness>Mandatory|Discretionary|Optional)\]\s*$"
)
_LEGACY_KEYWORD_RE = re.compile(r"^\s*-\s+(?:after|before)\s*:", re.IGNORECASE)


def parse_dependency_line(line: str, line_no: int) -> PrecedenceEdge:
    """Parse one dependency list item.

    Args:
        line: Raw markdown list line.
        line_no: 1-based line number within the section body (for errors).

    Returns:
        Edge with ``successor`` left empty for the caller to fill.

    Raises:
        ValueError: When the line uses ``after:`` / ``before:`` or does not
            match ``- <predecessor> [REL, Hardness]``.
    """
    if _LEGACY_KEYWORD_RE.match(line):
        msg = (
            f"invalid dependency syntax at line {line_no}: {line!r}; "
            "use predecessor name only "
            "(after:/before: are not allowed)"
        )
        raise ValueError(msg)
    match = _DEPENDENCY_RE.match(line)
    if match is None:
        msg = (
            f"invalid dependency syntax at line {line_no}: {line!r}; "
            "expected '- <predecessor> [FS, Mandatory]'"
        )
        raise ValueError(msg)
    return PrecedenceEdge(
        predecessor=match.group("predecessor"),
        successor="",  # filled by caller from context
        relation=RelationType(match.group("relation")),
        hardness=Hardness(match.group("hardness")),
    )


def parse_dependencies_section(body: str, *, successor: str) -> list[PrecedenceEdge]:
    """Parse dependency bullets; set ``successor`` on each edge.

    Args:
        body: Markdown body of the ``## Dependencies`` section.
        successor: Entity that owns the section (the dependent).

    Returns:
        Precedence edges from each listed predecessor to ``successor``.

    Raises:
        ValueError: When a non-empty, non-comment line is not valid syntax.
    """
    edges: list[PrecedenceEdge] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        edge = parse_dependency_line(line, lineno)
        edges.append(
            PrecedenceEdge(
                predecessor=edge.predecessor,
                successor=successor,
                relation=edge.relation,
                hardness=edge.hardness,
            )
        )
    return edges
