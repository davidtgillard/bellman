"""Roadmap filesystem layout, templates, and mutations."""

from __future__ import annotations

import shutil
from pathlib import Path

from snark.errors import SnarkLayoutError
from snark.naming import normalize_entity_name, validate_kebab

INITIATIVES_DIR = "initiatives"
PROJECTS_DIR = "projects"
MILESTONES_DIR = "milestones"
GOALS_DIR = "goals"
ARCHIVED_SUFFIX = ".archived.md"

WORK_SCOPE_SECTIONS = (
    "## Introduction\n\nTBD.\n\n"
    "## Motivation\n\nTBD.\n\n"
    "## Detailed Description\n\nTBD.\n\n"
    "## Dependencies\n\n"
)

PROJECT_EXTRA = "### Criteria for Success\n\nTBD.\n\n"

WORK_PACKAGES_TEMPLATE = """# Work packages

"""


def roadmap_root(path: Path | None) -> Path:
    """Resolve roadmap root (default: cwd)."""
    return path if path is not None else Path.cwd()


def ensure_roadmap_dirs(root: Path) -> None:
    """Create standard roadmap directories."""
    for name in (INITIATIVES_DIR, PROJECTS_DIR, MILESTONES_DIR, GOALS_DIR):
        (root / name).mkdir(parents=True, exist_ok=True)


def initiative_path(root: Path, name: str) -> Path:
    return root / INITIATIVES_DIR / f"{name}.md"


def archived_initiative_path(root: Path, name: str) -> Path:
    return root / INITIATIVES_DIR / f"{name}{ARCHIVED_SUFFIX}"


def project_dir(root: Path, name: str) -> Path:
    return root / PROJECTS_DIR / name


def project_md_path(root: Path, name: str) -> Path:
    return project_dir(root, name) / f"{name}.md"


def work_packages_path(root: Path, name: str) -> Path:
    return project_dir(root, name) / "work-packages.md"


def milestone_path(root: Path, name: str) -> Path:
    return root / MILESTONES_DIR / f"{name}.md"


def goal_path(root: Path, name: str) -> Path:
    return root / GOALS_DIR / f"{name}.md"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_initiative(root: Path, raw_name: str) -> Path:
    """Create ``initiatives/{name}.md``."""
    name = normalize_entity_name(raw_name)
    path = initiative_path(root, name)
    if path.exists():
        raise SnarkLayoutError(f"initiative already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\n{WORK_SCOPE_SECTIONS}"
    _write_text(path, content)
    return path


def create_project(root: Path, raw_name: str) -> Path:
    """Create project folder with description and work-packages files."""
    name = normalize_entity_name(raw_name.removesuffix(".md"))
    if raw_name.endswith(".md"):
        msg = "projects cannot be created as a single .md file"
        raise SnarkLayoutError(msg)
    pdir = project_dir(root, name)
    if pdir.exists():
        raise SnarkLayoutError(f"project already exists: {pdir}")
    title = name.replace("-", " ").title()
    scope = (
        f"# {title}\n\n"
        "## Introduction\n\nTBD.\n\n"
        "## Motivation\n\nTBD.\n\n"
        "## Detailed Description\n\nTBD.\n\n"
        f"{PROJECT_EXTRA}"
        "## Dependencies\n\n"
    )
    _write_text(project_md_path(root, name), scope)
    _write_text(work_packages_path(root, name), WORK_PACKAGES_TEMPLATE)
    return pdir


def create_milestone(root: Path, raw_name: str) -> Path:
    """Create ``milestones/{name}.md``."""
    name = normalize_entity_name(raw_name)
    path = milestone_path(root, name)
    if path.exists():
        raise SnarkLayoutError(f"milestone already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\n## Date\n\nYYYY-MM-DD\n\n## Description\n\nTBD.\n"
    _write_text(path, content)
    return path


def create_goal(root: Path, raw_name: str) -> Path:
    """Create ``goals/{name}.md``."""
    name = normalize_entity_name(raw_name)
    path = goal_path(root, name)
    if path.exists():
        raise SnarkLayoutError(f"goal already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\nTBD.\n"
    _write_text(path, content)
    return path


def find_entity(root: Path, name: str) -> tuple[str, Path]:
    """Locate an entity by natural name. Returns (kind, path)."""
    validate_kebab(name)
    candidates: list[tuple[str, Path]] = [
        ("initiative", initiative_path(root, name)),
        ("archived-initiative", archived_initiative_path(root, name)),
        ("project", project_dir(root, name)),
        ("milestone", milestone_path(root, name)),
        ("goal", goal_path(root, name)),
    ]
    found = [(kind, path) for kind, path in candidates if path.exists()]
    if not found:
        msg = f"no entity named {name!r} in roadmap at {root}"
        raise SnarkLayoutError(msg)
    if len(found) > 1:
        kinds = ", ".join(k for k, _ in found)
        msg = f"ambiguous name {name!r}: matches {kinds}"
        raise SnarkLayoutError(msg)
    return found[0]


def delete_entity(root: Path, name: str, *, force: bool = False) -> None:
    """Delete an initiative, project, milestone, or goal."""
    _ = force  # reserved for dependency checks in validate layer
    kind, path = find_entity(root, name)
    if kind == "project":
        shutil.rmtree(path)
    else:
        path.unlink()


def promote_initiative(root: Path, raw_name: str) -> Path:
    """Promote initiative to project; archive initiative file."""
    name = normalize_entity_name(raw_name)
    src = initiative_path(root, name)
    if not src.exists():
        msg = f"initiative not found: {src}"
        raise SnarkLayoutError(msg)
    if project_dir(root, name).exists():
        msg = f"project already exists: {name}"
        raise SnarkLayoutError(msg)
    content = src.read_text(encoding="utf-8")
    has_criteria = (
        "### Criteria for Success" in content or "## Criteria for Success" in content
    )
    if not has_criteria:
        content = content.rstrip() + "\n\n### Criteria for Success\n\nTBD.\n"
    pdir = project_dir(root, name)
    pdir.mkdir(parents=True)
    _write_text(project_md_path(root, name), content)
    _write_text(work_packages_path(root, name), WORK_PACKAGES_TEMPLATE)
    archive = archived_initiative_path(root, name)
    src.rename(archive)
    return pdir
