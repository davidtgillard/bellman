"""Parse ## Dependencies sections."""

from __future__ import annotations

import re

from bellman.model import Hardness, PrecedenceEdge, RelationType

_DEPENDENCY_RE = re.compile(
    r"^\s*-\s+after:\s*(?P<predecessor>\S+)\s*"
    r"\[(?P<relation>FF|FS|SF|SS),\s*(?P<hardness>Mandatory|Discretionary|Optional)\]\s*$"
)


def parse_dependency_line(line: str, line_no: int) -> PrecedenceEdge:
    """Parse one dependency list item."""
    match = _DEPENDENCY_RE.match(line)
    if match is None:
        msg = f"invalid dependency syntax at line {line_no}: {line!r}"
        raise ValueError(msg)
    return PrecedenceEdge(
        predecessor=match.group("predecessor"),
        successor="",  # filled by caller from context
        relation=RelationType(match.group("relation")),
        hardness=Hardness(match.group("hardness")),
    )


def parse_dependencies_section(body: str, *, successor: str) -> list[PrecedenceEdge]:
    """Parse dependency bullets; set ``successor`` on each edge."""
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
