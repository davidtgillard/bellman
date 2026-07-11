"""Roadmap filesystem layout, templates, and mutations."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from bellman.errors import BellmanLayoutError
from bellman.naming import normalize_entity_name, validate_kebab

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

WORK_PACKAGES_TEMPLATE = """version: 1

work_packages: []
"""


@dataclass(frozen=True, slots=True)
class DeletedEntity:
    """Entity removed by :func:`delete_entity`."""

    kind: str
    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class RenamedEntity:
    """Entity renamed by :func:`rename_entity`."""

    kind: str
    old_name: str
    new_name: str
    path: Path


_RENAMEABLE_KINDS = frozenset({"initiative", "project", "milestone", "goal"})

_SCOPE_DEPENDENCY_RE = re.compile(
    r"^(\s*-\s+after:\s*)(?P<predecessor>\S+)(\s*"
    r"\[(?:FF|FS|SF|SS),\s*(?:Mandatory|Discretionary|Optional)\]\s*)$"
)

_WP_DEPENDENCY_LINE_RE = re.compile(
    r"^(\s*-\s+after:\s*)(?P<predecessor>\S+)(\s*"
    r"\[(?:FF|FS|SF|SS),\s*(?:Mandatory|Discretionary|Optional)\]\s*)$"
)

_WP_DEPENDENCY_INLINE_RE = re.compile(
    r"^(\s*after:\s*)(?P<predecessor>\S+)(\s*"
    r"\[(?:FF|FS|SF|SS),\s*(?:Mandatory|Discretionary|Optional)\]\s*)$"
)

_WP_DEPENDENCY_DICT_AFTER_RE = re.compile(r"^(\s*after:\s*)(?P<predecessor>\S+)(\s*)$")


def _entity_name_from_path(kind: str, path: Path) -> str:
    if kind == "project":
        return path.name
    if path.name.endswith(ARCHIVED_SUFFIX):
        return path.name[: -len(ARCHIVED_SUFFIX)]
    return path.stem


_FITS_DIR = ".fits"
_GIT_DIR = ".git"


def roadmap_root(path: Path | None) -> Path:
    """Resolve roadmap root literally (default: cwd).

    Does not walk parent directories. Use :func:`discover_roadmap_root` when
    the caller should locate an existing initialized roadmap.

    Args:
        path: Explicit roadmap root, or ``None`` for the current directory.

    Returns:
        Resolved roadmap root path.
    """
    return path if path is not None else Path.cwd()


def _is_git_root(path: Path) -> bool:
    return (path / _GIT_DIR).exists()


def find_roadmap_root(start: Path) -> Path | None:
    """Walk upward from ``start`` and return the nearest ancestor with ``.fits/``.

    Stops at the git root (directory containing ``.git``) without crossing it.

    Args:
        start: Directory to begin searching from.

    Returns:
        The roadmap root when ``.fits/`` is found, otherwise ``None``.
    """
    current = start.resolve()
    while True:
        if (current / _FITS_DIR).is_dir():
            return current
        if _is_git_root(current):
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def discover_roadmap_root(path: Path | None = None) -> Path:
    """Resolve an initialized roadmap root by walking up from ``path`` or cwd.

    Stops at the git root (directory containing ``.git``) without crossing it.

    Args:
        path: Starting directory, or ``None`` for the current directory.

    Returns:
        The nearest ancestor directory containing ``.fits/``.

    Raises:
        BellmanLayoutError: When no ``.fits/`` directory is found within the
            search boundary.
    """
    start = path if path is not None else Path.cwd()
    found = find_roadmap_root(start)
    if found is None:
        msg = f"no initialized bellman roadmap found in {start} or ancestor directories"
        raise BellmanLayoutError(msg)
    return found


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
    return project_dir(root, name) / "work-packages.yaml"


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
        raise BellmanLayoutError(f"initiative already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\n{WORK_SCOPE_SECTIONS}"
    _write_text(path, content)
    return path


def create_project(root: Path, raw_name: str) -> Path:
    """Create project folder with description and work-packages files."""
    name = normalize_entity_name(raw_name.removesuffix(".md"))
    if raw_name.endswith(".md"):
        msg = "projects cannot be created as a single .md file"
        raise BellmanLayoutError(msg)
    pdir = project_dir(root, name)
    if pdir.exists():
        raise BellmanLayoutError(f"project already exists: {pdir}")
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
        raise BellmanLayoutError(f"milestone already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\n## Date\n\nYYYY-MM-DD\n\n## Description\n\nTBD.\n"
    _write_text(path, content)
    return path


def create_goal(root: Path, raw_name: str) -> Path:
    """Create ``goals/{name}.md``."""
    name = normalize_entity_name(raw_name)
    path = goal_path(root, name)
    if path.exists():
        raise BellmanLayoutError(f"goal already exists: {path}")
    title = name.replace("-", " ").title()
    content = f"# {title}\n\nTBD.\n"
    _write_text(path, content)
    return path


_LAYOUT_DIRS = (INITIATIVES_DIR, PROJECTS_DIR, MILESTONES_DIR, GOALS_DIR)


def _is_path_shaped_ref(ref: str) -> bool:
    if ref.endswith(".md"):
        return True
    if "/" in ref or "\\" in ref:
        return True
    return any(ref.startswith(f"{d}/") for d in _LAYOUT_DIRS)


def resolve_entity_path(root: Path, ref: str) -> tuple[str, Path]:
    """Locate an entity by layout-relative path. Returns (kind, path).

    Args:
        root: Roadmap root directory.
        ref: Path relative to ``root`` (e.g. ``goals/foo.md``, ``projects/foo``).

    Returns:
        Entity kind string and resolved filesystem path.

    Raises:
        BellmanLayoutError: When the path is invalid, escapes the roadmap root,
            or does not match a known entity layout.
    """
    normalized = ref.replace("\\", "/").strip("/")
    if not normalized or ".." in normalized.split("/"):
        msg = f"invalid entity path {ref!r}"
        raise BellmanLayoutError(msg)

    candidate = (root / normalized).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        msg = f"entity path {ref!r} is outside roadmap at {root}"
        raise BellmanLayoutError(msg) from exc

    rel = candidate.relative_to(root_resolved)
    parts = rel.parts
    if not parts:
        msg = f"invalid entity path {ref!r}"
        raise BellmanLayoutError(msg)

    top = parts[0]
    if top == GOALS_DIR:
        if len(parts) != 2 or not parts[1].endswith(".md"):
            msg = f"invalid goal path {ref!r}; expected goals/{{name}}.md"
            raise BellmanLayoutError(msg)
        path = root_resolved / rel
        if not path.is_file():
            msg = f"no entity at {ref!r} in roadmap at {root}"
            raise BellmanLayoutError(msg)
        return "goal", path

    if top == MILESTONES_DIR:
        if len(parts) != 2 or not parts[1].endswith(".md"):
            msg = f"invalid milestone path {ref!r}; expected milestones/{{name}}.md"
            raise BellmanLayoutError(msg)
        path = root_resolved / rel
        if not path.is_file():
            msg = f"no entity at {ref!r} in roadmap at {root}"
            raise BellmanLayoutError(msg)
        return "milestone", path

    if top == INITIATIVES_DIR:
        if len(parts) != 2 or not parts[1].endswith(".md"):
            msg = f"invalid initiative path {ref!r}; expected initiatives/{{name}}.md"
            raise BellmanLayoutError(msg)
        path = root_resolved / rel
        if not path.is_file():
            msg = f"no entity at {ref!r} in roadmap at {root}"
            raise BellmanLayoutError(msg)
        if path.name.endswith(ARCHIVED_SUFFIX):
            return "archived-initiative", path
        return "initiative", path

    if top == PROJECTS_DIR:
        if len(parts) == 2 and not parts[1].endswith(".md"):
            path = root_resolved / rel
            if not path.is_dir():
                msg = f"no entity at {ref!r} in roadmap at {root}"
                raise BellmanLayoutError(msg)
            return "project", path
        if len(parts) == 1:
            path = root_resolved / rel
            if not path.is_dir():
                msg = f"no entity at {ref!r} in roadmap at {root}"
                raise BellmanLayoutError(msg)
            return "project", path
        if len(parts) == 2 and parts[1].endswith(".md"):
            path = root_resolved / rel
            if not path.is_file():
                msg = f"no entity at {ref!r} in roadmap at {root}"
                raise BellmanLayoutError(msg)
            project_name = parts[1][:-3]
            if parts[1] != f"{project_name}.md":
                msg = (
                    f"invalid project path {ref!r}; "
                    "expected projects/{name}/{name}.md"
                )
                raise BellmanLayoutError(msg)
            return "project", path.parent
        msg = (
            f"invalid project path {ref!r}; "
            "expected projects/{name} or projects/{name}/{name}.md"
        )
        raise BellmanLayoutError(msg)

    msg = f"invalid entity path {ref!r}; must be under {', '.join(_LAYOUT_DIRS)}"
    raise BellmanLayoutError(msg)


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
        raise BellmanLayoutError(msg)
    if len(found) > 1:
        kinds = ", ".join(k for k, _ in found)
        msg = f"ambiguous name {name!r}: matches {kinds}"
        raise BellmanLayoutError(msg)
    return found[0]


def find_entity_by_kind(root: Path, kind: str, name: str) -> tuple[str, Path]:
    """Locate an entity by explicit kind and natural name.

    Args:
        root: Roadmap root directory.
        kind: Entity kind (``initiative``, ``project``, ``milestone``, ``goal``).
        name: Natural entity name (kebab-case).

    Returns:
        Resolved kind string and filesystem path.

    Raises:
        BellmanLayoutError: When ``kind`` is unknown or no matching entity exists.
    """
    if kind not in _RENAMEABLE_KINDS:
        kinds = ", ".join(sorted(_RENAMEABLE_KINDS))
        msg = f"unknown entity kind {kind!r}; expected one of: {kinds}"
        raise BellmanLayoutError(msg)
    validate_kebab(name)
    if kind == "project":
        path = project_dir(root, name)
        if not path.is_dir():
            msg = f"no project named {name!r} in roadmap at {root}"
            raise BellmanLayoutError(msg)
        return "project", path
    if kind == "initiative":
        path = initiative_path(root, name)
        if path.is_file():
            return "initiative", path
        msg = f"no initiative named {name!r} in roadmap at {root}"
        raise BellmanLayoutError(msg)
    if kind == "milestone":
        path = milestone_path(root, name)
        if path.is_file():
            return "milestone", path
        msg = f"no milestone named {name!r} in roadmap at {root}"
        raise BellmanLayoutError(msg)
    path = goal_path(root, name)
    if path.is_file():
        return "goal", path
    msg = f"no goal named {name!r} in roadmap at {root}"
    raise BellmanLayoutError(msg)


def _destination_exists(root: Path, kind: str, name: str) -> bool:
    if kind == "project":
        return project_dir(root, name).exists()
    if kind == "archived-initiative":
        return archived_initiative_path(root, name).exists()
    if kind == "initiative":
        return initiative_path(root, name).exists()
    if kind == "milestone":
        return milestone_path(root, name).exists()
    return goal_path(root, name).exists()


def _rewrite_predecessor_ref(predecessor: str, old_name: str, new_name: str) -> str:
    project_prefix = f"{old_name}/"
    if predecessor == old_name:
        return new_name
    if predecessor.startswith(project_prefix):
        return f"{new_name}/{predecessor[len(project_prefix) :]}"
    return predecessor


def _rewrite_scope_dependency_line(
    line: str,
    *,
    old_name: str,
    new_name: str,
) -> str:
    match = _SCOPE_DEPENDENCY_RE.match(line)
    if match is None:
        return line
    predecessor = match.group("predecessor")
    updated = _rewrite_predecessor_ref(predecessor, old_name, new_name)
    if updated == predecessor:
        return line
    return f"{match.group(1)}{updated}{match.group(3)}"


def _rewrite_work_packages_line(
    line: str,
    *,
    old_name: str,
    new_name: str,
) -> str:
    for pattern in (
        _WP_DEPENDENCY_LINE_RE,
        _WP_DEPENDENCY_INLINE_RE,
        _WP_DEPENDENCY_DICT_AFTER_RE,
    ):
        match = pattern.match(line)
        if match is None:
            continue
        predecessor = match.group("predecessor")
        updated = _rewrite_predecessor_ref(predecessor, old_name, new_name)
        if updated == predecessor:
            return line
        return f"{match.group(1)}{updated}{match.group(3)}"
    return line


def _rewrite_dependency_refs(root: Path, *, old_name: str, new_name: str) -> None:
    initiatives_dir = root / INITIATIVES_DIR
    if initiatives_dir.is_dir():
        for path in initiatives_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            lines = [
                _rewrite_scope_dependency_line(
                    line,
                    old_name=old_name,
                    new_name=new_name,
                )
                for line in text.splitlines(keepends=True)
            ]
            path.write_text("".join(lines), encoding="utf-8")

    projects_dir = root / PROJECTS_DIR
    if projects_dir.is_dir():
        for pdir in projects_dir.iterdir():
            if not pdir.is_dir():
                continue
            md_path = pdir / f"{pdir.name}.md"
            if md_path.is_file():
                text = md_path.read_text(encoding="utf-8")
                lines = [
                    _rewrite_scope_dependency_line(
                        line,
                        old_name=old_name,
                        new_name=new_name,
                    )
                    for line in text.splitlines(keepends=True)
                ]
                md_path.write_text("".join(lines), encoding="utf-8")
            wp_path = pdir / "work-packages.yaml"
            if wp_path.is_file():
                text = wp_path.read_text(encoding="utf-8")
                lines = [
                    _rewrite_work_packages_line(
                        line,
                        old_name=old_name,
                        new_name=new_name,
                    )
                    for line in text.splitlines(keepends=True)
                ]
                wp_path.write_text("".join(lines), encoding="utf-8")


def _update_goal_heading(path: Path, new_name: str) -> None:
    title = new_name.replace("-", " ").title()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}\n"
            break
    path.write_text("".join(lines), encoding="utf-8")


def _move_markdown_entity(path: Path, new_path: Path) -> None:
    if new_path.exists():
        msg = f"entity already exists: {new_path}"
        raise BellmanLayoutError(msg)
    path.rename(new_path)


def _rename_project(root: Path, old_name: str, new_name: str) -> Path:
    old_dir = project_dir(root, old_name)
    new_dir = project_dir(root, new_name)
    if new_dir.exists():
        msg = f"project already exists: {new_dir}"
        raise BellmanLayoutError(msg)
    old_dir.rename(new_dir)
    old_md = new_dir / f"{old_name}.md"
    new_md = project_md_path(root, new_name)
    if old_md.exists():
        old_md.rename(new_md)
    return new_dir


def rename_entity(
    root: Path,
    old_ref: str,
    raw_new_name: str,
    *,
    kind: str | None = None,
) -> RenamedEntity:
    """Rename an initiative, project, milestone, or goal.

    Args:
        root: Roadmap root directory.
        old_ref: Natural entity name or layout-relative path (e.g. ``goals/foo.md``).
        raw_new_name: New natural name (kebab-case).
        kind: When set, resolve ``old_ref`` as that entity kind only.

    Returns:
        Kind, old and new names, and the renamed entity path.

    Raises:
        BellmanLayoutError: When the entity cannot be resolved, the destination
            exists, or the rename fails.
        ValueError: When ``raw_new_name`` is not valid kebab-case.
    """
    new_name = normalize_entity_name(raw_new_name)
    if kind is None:
        if _is_path_shaped_ref(old_ref):
            resolved_kind, path = resolve_entity_path(root, old_ref)
        else:
            resolved_kind, path = find_entity(root, old_ref)
    else:
        old_name = normalize_entity_name(old_ref)
        resolved_kind, path = find_entity_by_kind(root, kind, old_name)
    old_name = _entity_name_from_path(resolved_kind, path)
    if old_name == new_name:
        msg = f"entity already named {new_name!r}"
        raise BellmanLayoutError(msg)
    if _destination_exists(root, resolved_kind, new_name):
        msg = f"{resolved_kind} already exists: {new_name!r}"
        raise BellmanLayoutError(msg)

    if resolved_kind == "project":
        new_path = _rename_project(root, old_name, new_name)
    elif resolved_kind == "archived-initiative":
        new_path = archived_initiative_path(root, new_name)
        _move_markdown_entity(path, new_path)
    elif resolved_kind == "initiative":
        new_path = initiative_path(root, new_name)
        _move_markdown_entity(path, new_path)
    elif resolved_kind == "milestone":
        new_path = milestone_path(root, new_name)
        _move_markdown_entity(path, new_path)
    else:
        new_path = goal_path(root, new_name)
        _move_markdown_entity(path, new_path)
        _update_goal_heading(new_path, new_name)

    _rewrite_dependency_refs(root, old_name=old_name, new_name=new_name)
    return RenamedEntity(
        kind=resolved_kind,
        old_name=old_name,
        new_name=new_name,
        path=new_path,
    )


def delete_entity(root: Path, ref: str, *, force: bool = False) -> DeletedEntity:
    """Delete an initiative, project, milestone, or goal.

    Args:
        root: Roadmap root directory.
        ref: Natural entity name or layout-relative path (e.g. ``goals/foo.md``).
        force: Reserved for future dependency checks.

    Returns:
        Kind, natural name, and deleted path for the removed entity.

    Raises:
        BellmanLayoutError: When the entity cannot be resolved or deleted.
    """
    _ = force  # reserved for dependency checks in validate layer
    if _is_path_shaped_ref(ref):
        kind, path = resolve_entity_path(root, ref)
    else:
        kind, path = find_entity(root, ref)
    name = _entity_name_from_path(kind, path)
    if kind == "project":
        shutil.rmtree(path)
    else:
        path.unlink()
    return DeletedEntity(kind=kind, name=name, path=path)


def promote_initiative(root: Path, raw_name: str) -> Path:
    """Promote initiative to project; archive initiative file."""
    name = normalize_entity_name(raw_name)
    src = initiative_path(root, name)
    if not src.exists():
        msg = f"initiative not found: {src}"
        raise BellmanLayoutError(msg)
    if project_dir(root, name).exists():
        msg = f"project already exists: {name}"
        raise BellmanLayoutError(msg)
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
