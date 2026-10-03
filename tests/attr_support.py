"""Helpers for building throwaway roadmaps that use attributes."""

from __future__ import annotations

from pathlib import Path

from bellman import layout

PRIORITY_JSONC = """{
  "name": "priority",
  "version": "1.0",
  "applies_to": ["initiative", "project"],
  "cardinality": "one",
  "required": true,
  "values": ["P0", "P1", "P2"]
}
"""

PROGRAM_JSONC = """{
  // Speculative work scope with data per program.
  "name": "program",
  "version": "1.2",
  "applies_to": ["initiative", "project", "work_package"],
  "cardinality": "many",
  "values": {
    "platform-v2": { "title": "Platform v2", "probability": 0.4 },
    "data-residency": { "title": "EU data residency" },
  },
  "value_schema": {
    "type": "object",
    "required": ["title"],
    "properties": {
      "title": { "type": "string" },
      "probability": { "type": "number", "minimum": 0, "maximum": 1 }
    }
  },
  "assignment_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": { "allocation": { "type": "number", "minimum": 0, "maximum": 1 } }
  }
}
"""

BUDGET_JSONC = """{
  "name": "budget",
  "version": "1.0",
  "applies_to": ["project", "milestone", "goal"],
  "cardinality": "one",
  "value_schema": { "type": "number", "minimum": 0 }
}
"""

SCOPE_BODY = (
    "## Introduction\n\nIntro.\n\n"
    "## Motivation\n\nWhy.\n\n"
    "## Detailed Description\n\nWhat.\n\n"
)


def make_root(path: Path) -> Path:
    """Create the standard directories and a ``.fits`` marker under ``path``."""
    layout.ensure_roadmap_dirs(path)
    (path / ".fits").mkdir(exist_ok=True)
    return path


def write_attribute(root: Path, name: str, text: str) -> Path:
    """Write ``attributes/{name}.jsonc``."""
    target = root / layout.ATTRIBUTES_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{name}.jsonc"
    path.write_text(text, encoding="utf-8")
    return path


def classifications_section(lines: list[str] | None) -> str:
    """Render a ``## Classifications`` section from bullet bodies."""
    if lines is None:
        return ""
    bullets = "".join(f"- {line}\n" for line in lines)
    return f"\n## Classifications\n\n{bullets}"


def write_initiative(
    root: Path,
    name: str,
    classifications: list[str] | None = None,
) -> Path:
    """Write an initiative with optional classification bullets."""
    title = name.replace("-", " ").title()
    path = root / layout.INITIATIVES_DIR / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {title}\n\n{SCOPE_BODY}## Dependencies\n"
        + classifications_section(classifications),
        encoding="utf-8",
    )
    return path


def write_project(
    root: Path,
    name: str,
    classifications: list[str] | None = None,
    work_packages: str | None = None,
) -> Path:
    """Write a project (and optional ``work-packages.yaml``)."""
    title = name.replace("-", " ").title()
    pdir = root / layout.PROJECTS_DIR / name
    pdir.mkdir(parents=True, exist_ok=True)
    md = pdir / f"{name}.md"
    md.write_text(
        f"# {title}\n\n{SCOPE_BODY}### Criteria for Success\n\nShip it.\n\n"
        "## Dependencies\n" + classifications_section(classifications),
        encoding="utf-8",
    )
    if work_packages is not None:
        (pdir / "work-packages.yaml").write_text(work_packages, encoding="utf-8")
    return md


def write_goal(
    root: Path,
    name: str,
    classifications: list[str] | None = None,
) -> Path:
    """Write a goal with optional classification bullets."""
    title = name.replace("-", " ").title()
    path = root / layout.GOALS_DIR / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {title}\n\nKeep it low.\n" + classifications_section(classifications),
        encoding="utf-8",
    )
    return path


def write_milestone(
    root: Path,
    name: str,
    classifications: list[str] | None = None,
) -> Path:
    """Write a milestone with optional classification bullets."""
    title = name.replace("-", " ").title()
    path = root / layout.MILESTONES_DIR / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {title}\n\n## Date\n\n2026-09-30\n\n## Description\n\nShip.\n"
        + classifications_section(classifications),
        encoding="utf-8",
    )
    return path


def wp_yaml(*blocks: str) -> str:
    """Join work-package YAML blocks under a ``work_packages`` list."""
    return "version: 1\n\nwork_packages:\n" + "".join(blocks)


def wp_block(title: str, classifications: str = "", extra: str = "") -> str:
    """One leaf work package with optional indented ``classifications`` lines."""
    block = f"  - title: {title}\n    description: Do it.\n    estimate: [1d, 2d, 3d]\n"
    if classifications:
        block += "    classifications:\n" + classifications
    return block + extra
