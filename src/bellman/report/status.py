"""Roadmap status inventory: entity health and registry alignment."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

from pyfits.result import Err, Ok, Result

from bellman import layout
from bellman.errors import BellmanError
from bellman.graph.delta import (
    RegistryDelta,
    RegistryDeltaError,
    compute_registry_delta,
)
from bellman.graph.desired import (
    DesiredNode,
    entity_node_id,
    flatten_wps,
    goal_node_id,
    milestone_node_id,
    natural_name_from_node_id,
    scope_node_id,
    wp_node_id,
)
from bellman.model import Roadmap
from bellman.roadmap import load_for_validation
from bellman.validate import ValidationResult, layout_wp_path, validate_roadmap

EntityKind = Literal[
    "initiative",
    "archived_initiative",
    "project",
    "work_package",
    "milestone",
    "goal",
]
"""Kind of roadmap entity shown in a status inventory row."""

MarkdownHealth = Literal["ok", "warning", "invalid", "unparsed"]
"""Markdown health for one inventory entity."""

RegistryHealth = Literal["synced", "missing", "extra", "n/a"]
"""Registry alignment for one inventory entity."""

_WP_PATH_RE = re.compile(
    r"[\\/]projects[\\/]([^\\/]+)[\\/]work-packages\.yaml\s+\(([^)]+)\)\s*$"
)
_SECTION_ORDER: tuple[EntityKind, ...] = (
    "initiative",
    "archived_initiative",
    "project",
    "work_package",
    "milestone",
    "goal",
)
_SECTION_TITLES: dict[EntityKind, str] = {
    "initiative": "Initiatives",
    "archived_initiative": "Archived initiatives",
    "project": "Projects",
    "work_package": "Work packages",
    "milestone": "Milestones",
    "goal": "Goals",
}


@dataclass(frozen=True, slots=True)
class EntityStatus:
    """Status row for one roadmap entity.

    Attributes:
        kind: Entity kind.
        name: Natural name; work packages use ``project/slug``.
        path: Markdown or YAML path when known.
        markdown: Markdown health classification.
        issues: Load errors, validation errors, and warnings for this entity.
        registry: Registry alignment classification.
        node: Desired graph node for this entity when applicable.
    """

    kind: EntityKind
    name: str
    path: str | None
    markdown: MarkdownHealth
    issues: tuple[str, ...]
    registry: RegistryHealth
    node: DesiredNode | None = None


@dataclass(frozen=True, slots=True)
class RoadmapStatus:
    """Full roadmap status snapshot for reporting.

    Attributes:
        root: Absolute roadmap root path.
        entities: Inventory rows in display order.
        global_issues: Cross-entity errors not tied to a single entity.
        registry: Computed registry delta when comparison succeeded.
        registry_error: Human-readable reason when registry was not compared.
    """

    root: str
    entities: tuple[EntityStatus, ...]
    global_issues: tuple[str, ...]
    registry: RegistryDelta | None
    registry_error: str | None


def compute_roadmap_status(
    root: Path,
    *,
    registry: bool = True,
) -> Result[RoadmapStatus, str]:
    """Compute a read-only status inventory for ``root``.

    Args:
        root: Roadmap root directory.
        registry: When True, compare markdown to the pyfits registry.

    Returns:
        ``Ok(RoadmapStatus)`` with entity inventory and optional registry delta.
        ``Err(str)`` when registry comparison fails unexpectedly after being
        requested (for example a libfits graph read error). Soft skip reasons
        such as missing libfits are returned inside ``Ok`` via
        ``registry_error``.
    """
    load_result = load_for_validation(root)
    roadmap = load_result.roadmap
    validation = validate_roadmap(roadmap)
    combined = ValidationResult(
        errors=load_result.errors + validation.errors,
        warnings=validation.warnings,
    )

    issue_index, global_issues = _index_issues(
        root, roadmap, combined, load_result.errors
    )
    entities = _build_entities(root, roadmap, load_result.errors, issue_index)

    delta: RegistryDelta | None = None
    registry_error: str | None = None
    if not registry:
        registry_error = "Registry check skipped (--no-registry)."
    else:
        delta_result = compute_registry_delta(root, roadmap)
        if isinstance(delta_result, Err):
            err = delta_result.err_value
            if isinstance(err, RegistryDeltaError):
                soft = _is_soft_registry_skip(err.message)
                if soft:
                    registry_error = err.format()
                else:
                    return Err(err.format())
            else:
                return Err(str(err))
        else:
            delta = delta_result.ok_value

    entities = _apply_registry(entities, delta)
    return Ok(
        RoadmapStatus(
            root=str(root.resolve()),
            entities=tuple(entities),
            global_issues=tuple(global_issues),
            registry=delta,
            registry_error=registry_error,
        )
    )


def format_status_report(status: RoadmapStatus, io: TextIO) -> None:
    """Write a human-readable status report to ``io``.

    Args:
        status: Computed roadmap status.
        io: Output stream (typically stdout).
    """
    io.write(f"Roadmap: {status.root}\n")

    if status.global_issues:
        io.write("\nGlobal issues\n")
        for issue in status.global_issues:
            io.write(f"  {issue}\n")

    for kind in _SECTION_ORDER:
        rows = [e for e in status.entities if e.kind == kind]
        if not rows:
            continue
        title = _SECTION_TITLES[kind]
        if kind == "work_package":
            by_project: dict[str, list[EntityStatus]] = defaultdict(list)
            for row in rows:
                project_name, _, slug = row.name.partition("/")
                by_project[project_name].append(
                    EntityStatus(
                        kind=row.kind,
                        name=slug or row.name,
                        path=row.path,
                        markdown=row.markdown,
                        issues=row.issues,
                        registry=row.registry,
                        node=row.node,
                    )
                )
            for project_name in sorted(by_project):
                project_rows = by_project[project_name]
                io.write(f"\n{title} ({len(project_rows)}) — {project_name}\n")
                _write_entity_rows(project_rows, io)
        else:
            io.write(f"\n{title} ({len(rows)})\n")
            _write_entity_rows(rows, io)

    io.write("\nRegistry\n")
    if status.registry_error is not None:
        io.write(f"  {status.registry_error}\n")
    elif status.registry is not None:
        _write_registry_section(status.registry, io)
    else:
        io.write("  Registry check not available.\n")

    io.write(f"\nSummary: {_summary_line(status)}\n")


def _write_entity_rows(rows: list[EntityStatus], io: TextIO) -> None:
    name_width = max((len(row.name) for row in rows), default=0)
    for row in rows:
        line = f"  {row.name:<{name_width}}  {row.markdown}"
        if row.registry not in ("n/a", "synced"):
            line += f"  registry: {row.registry}"
        if row.issues:
            line += f"  {row.issues[0]}"
        io.write(f"{line}\n")
        for extra in row.issues[1:]:
            io.write(f"  {'':<{name_width}}  {extra}\n")


def _write_registry_section(delta: RegistryDelta, io: TextIO) -> None:
    io.write(
        f"  Nodes: {delta.desired_node_count} desired, "
        f"{delta.actual_node_count} actual "
        f"({len(delta.missing_nodes)} missing, {len(delta.extra_nodes)} extra)\n"
    )
    io.write(
        f"  Links: {delta.desired_link_count} desired, "
        f"{delta.actual_link_count} actual "
        f"({len(delta.missing_links)} missing, {len(delta.extra_links)} extra)\n"
    )
    if delta.missing_nodes:
        io.write("  Missing nodes:\n")
        for node in delta.missing_nodes:
            io.write(f"    {node}\n")
    if delta.extra_nodes:
        io.write("  Extra nodes:\n")
        for node in delta.extra_nodes:
            io.write(f"    {node}\n")
    if delta.missing_links:
        io.write("  Missing links:\n")
        for link in delta.missing_links:
            io.write(f"    {link}\n")
    if delta.extra_links:
        io.write("  Extra links:\n")
        for link in delta.extra_links:
            io.write(f"    {link}\n")
    migration = "yes" if delta.needs_id_migration else "no"
    io.write(f"  Legacy ID migration: {migration}\n")
    if not delta.has_differences:
        io.write("  Registry matches git.\n")


def _summary_line(status: RoadmapStatus) -> str:
    invalid = sum(1 for e in status.entities if e.markdown == "invalid")
    unparsed = sum(1 for e in status.entities if e.markdown == "unparsed")
    warnings = sum(1 for e in status.entities if e.markdown == "warning")
    parts = [
        f"{invalid + unparsed} invalid",
        f"{warnings} warning",
    ]
    if status.registry is not None:
        node_deltas = len(status.registry.missing_nodes) + len(
            status.registry.extra_nodes
        )
        link_deltas = len(status.registry.missing_links) + len(
            status.registry.extra_links
        )
        parts.append(f"{node_deltas} registry node delta")
        parts.append(f"{link_deltas} registry link delta")
    elif status.registry_error is not None:
        parts.append("registry not checked")
    if status.global_issues:
        parts.append(f"{len(status.global_issues)} global issue")
    return ", ".join(parts)


def _is_soft_registry_skip(message: str) -> bool:
    lowered = message.lower()
    return (
        "libfits not available" in lowered
        or "not initialized" in lowered
        or "run bellman init" in lowered
    )


def _entity_key(kind: EntityKind, name: str) -> str:
    return f"{kind}:{name}"


def _index_issues(
    root: Path,
    roadmap: Roadmap,
    result: ValidationResult,
    load_errors: tuple[BellmanError, ...],
) -> tuple[dict[str, list[str]], list[str]]:
    path_to_key = _path_key_map(root, roadmap)
    indexed: dict[str, list[str]] = defaultdict(list)
    global_issues: list[str] = []

    for err in result.errors:
        key = _key_for_issue_path(root, err.path, path_to_key)
        message = err.format()
        if key is None:
            global_issues.append(message)
        else:
            indexed[key].append(message)

    for warn in result.warnings:
        key = _key_for_issue_path(root, warn.path, path_to_key)
        message = f"warning: {warn.format()}"
        if key is None:
            global_issues.append(message)
        else:
            indexed[key].append(message)

    # Ensure load errors for unparsed files are indexed even when the entity
    # is not present on the roadmap snapshot.
    for err in load_errors:
        key = _key_for_issue_path(root, err.path, path_to_key)
        if key is None:
            inferred = _infer_entity_from_path(root, err.path)
            if inferred is not None:
                key = _entity_key(inferred[0], inferred[1])
                path_to_key[_normalize_path(err.path)] = key
        if key is not None and err.format() not in indexed[key]:
            indexed[key].append(err.format())

    return indexed, global_issues


def _path_key_map(root: Path, roadmap: Roadmap) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for initiative in roadmap.initiatives:
        mapping[_normalize_path(initiative.path)] = _entity_key(
            "initiative", initiative.name
        )
    for archived in roadmap.archived_initiatives:
        mapping[_normalize_path(archived.path)] = _entity_key(
            "archived_initiative", archived.name
        )
        mapping[
            _normalize_path(str(layout.archived_initiative_path(root, archived.name)))
        ] = _entity_key("archived_initiative", archived.name)
    for project in roadmap.projects:
        mapping[_normalize_path(project.path)] = _entity_key("project", project.name)
        mapping[_normalize_path(str(layout.project_md_path(root, project.name)))] = (
            _entity_key("project", project.name)
        )
        for wp, _ in flatten_wps(project.work_packages, None, project.name):
            wp_path = layout_wp_path(roadmap, project.name, wp.slug)
            mapping[_normalize_path(wp_path)] = _entity_key(
                "work_package", f"{project.name}/{wp.slug}"
            )
    for milestone in roadmap.milestones:
        mapping[_normalize_path(milestone.path)] = _entity_key(
            "milestone", milestone.name
        )
    for goal in roadmap.goals:
        mapping[_normalize_path(goal.path)] = _entity_key("goal", goal.name)
    return mapping


def _normalize_path(path_str: str) -> str:
    return str(Path(path_str))


def _key_for_issue_path(
    root: Path,
    path_str: str,
    path_to_key: dict[str, str],
) -> str | None:
    normalized = _normalize_path(path_str)
    if normalized in path_to_key:
        return path_to_key[normalized]
    try:
        if Path(path_str).resolve() == root.resolve():
            return None
    except OSError:
        if path_str in {str(root), str(root.resolve())}:
            return None

    match = _WP_PATH_RE.search(path_str.replace("\\", "/"))
    if match is not None:
        project_name, slug = match.group(1), match.group(2)
        return _entity_key("work_package", f"{project_name}/{slug}")

    inferred = _infer_entity_from_path(root, path_str)
    if inferred is not None:
        return _entity_key(inferred[0], inferred[1])
    return None


def _infer_entity_from_path(root: Path, path_str: str) -> tuple[EntityKind, str] | None:
    """Derive kind/name from a filesystem path when the entity failed to load."""
    try:
        rel = Path(path_str).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        try:
            rel = Path(path_str).relative_to(root)
        except ValueError:
            return None

    parts = rel.parts
    if (
        len(parts) == 2
        and parts[0] == layout.INITIATIVES_DIR
        and parts[1].endswith(".md")
    ):
        filename = parts[1]
        if filename.endswith(layout.ARCHIVED_SUFFIX):
            name = filename[: -len(layout.ARCHIVED_SUFFIX)]
            return "archived_initiative", name
        return "initiative", Path(filename).stem
    if (
        len(parts) == 3
        and parts[0] == layout.PROJECTS_DIR
        and parts[2] == f"{parts[1]}.md"
    ):
        return "project", parts[1]
    if (
        len(parts) == 3
        and parts[0] == layout.PROJECTS_DIR
        and parts[2] == "work-packages.yaml"
    ):
        return "project", parts[1]
    if (
        len(parts) == 2
        and parts[0] == layout.MILESTONES_DIR
        and parts[1].endswith(".md")
    ):
        return "milestone", Path(parts[1]).stem
    if len(parts) == 2 and parts[0] == layout.GOALS_DIR and parts[1].endswith(".md"):
        return "goal", Path(parts[1]).stem
    return None


def _markdown_health(
    *,
    issues: list[str],
    unparsed: bool,
) -> MarkdownHealth:
    if unparsed:
        return "unparsed"
    if any(not issue.startswith("warning: ") for issue in issues):
        return "invalid"
    if issues:
        return "warning"
    return "ok"


def _build_entities(
    root: Path,
    roadmap: Roadmap,
    load_errors: tuple[BellmanError, ...],
    issue_index: dict[str, list[str]],
) -> list[EntityStatus]:
    entities: list[EntityStatus] = []
    seen_keys: set[str] = set()

    def add(
        *,
        kind: EntityKind,
        name: str,
        path: str | None,
        node: DesiredNode | None,
        unparsed: bool = False,
    ) -> None:
        key = _entity_key(kind, name)
        if key in seen_keys:
            return
        seen_keys.add(key)
        issues = tuple(issue_index.get(key, ()))
        entities.append(
            EntityStatus(
                kind=kind,
                name=name,
                path=path,
                markdown=_markdown_health(issues=list(issues), unparsed=unparsed),
                issues=issues,
                registry="n/a",
                node=node,
            )
        )

    for initiative in roadmap.initiatives:
        add(
            kind="initiative",
            name=initiative.name,
            path=initiative.path,
            node=DesiredNode("initiative", scope_node_id(initiative)),
        )
    for archived in roadmap.archived_initiatives:
        node = None
        if roadmap.project_by_name(archived.name) is None:
            node = DesiredNode("initiative", scope_node_id(archived))
        add(
            kind="archived_initiative",
            name=archived.name,
            path=archived.path,
            node=node,
        )
    for project in roadmap.projects:
        add(
            kind="project",
            name=project.name,
            path=project.path,
            node=DesiredNode("project", scope_node_id(project)),
        )
        for wp, _ in flatten_wps(project.work_packages, None, project.name):
            add(
                kind="work_package",
                name=f"{project.name}/{wp.slug}",
                path=layout_wp_path(roadmap, project.name, wp.slug),
                node=DesiredNode("work_package", wp_node_id(project.name, wp.slug)),
            )
    for milestone in roadmap.milestones:
        add(
            kind="milestone",
            name=milestone.name,
            path=milestone.path,
            node=DesiredNode("milestone", milestone_node_id(milestone.name)),
        )
    for goal in roadmap.goals:
        add(
            kind="goal",
            name=goal.name,
            path=goal.path,
            node=DesiredNode("goal", goal_node_id(goal.name)),
        )

    for err in load_errors:
        inferred = _infer_entity_from_path(root, err.path)
        if inferred is None:
            continue
        kind, name = inferred
        key = _entity_key(kind, name)
        if key in seen_keys:
            continue
        node = _node_for_kind_name(kind, name)
        add(kind=kind, name=name, path=err.path, node=node, unparsed=True)

    return entities


def _node_for_kind_name(kind: EntityKind, name: str) -> DesiredNode | None:
    if kind in ("initiative", "archived_initiative"):
        return DesiredNode("initiative", entity_node_id("initiative", name))
    if kind == "project":
        return DesiredNode("project", entity_node_id("project", name))
    if kind == "work_package":
        project_name, _, slug = name.partition("/")
        if not slug:
            return None
        return DesiredNode("work_package", wp_node_id(project_name, slug))
    if kind == "milestone":
        return DesiredNode("milestone", milestone_node_id(name))
    return DesiredNode("goal", goal_node_id(name))


def _apply_registry(
    entities: list[EntityStatus],
    delta: RegistryDelta | None,
) -> list[EntityStatus]:
    if delta is None:
        return [
            EntityStatus(
                kind=e.kind,
                name=e.name,
                path=e.path,
                markdown=e.markdown,
                issues=e.issues,
                registry="n/a",
                node=e.node,
            )
            for e in entities
        ]

    missing = delta.missing_node_ids
    extra = delta.extra_node_ids
    updated: list[EntityStatus] = []
    covered_extra: set[DesiredNode] = set()

    for entity in entities:
        registry: RegistryHealth = "n/a"
        if entity.node is not None:
            if entity.node in missing:
                registry = "missing"
            elif entity.node in extra:
                registry = "extra"
                covered_extra.add(entity.node)
            else:
                registry = "synced"
        updated.append(
            EntityStatus(
                kind=entity.kind,
                name=entity.name,
                path=entity.path,
                markdown=entity.markdown,
                issues=entity.issues,
                registry=registry,
                node=entity.node,
            )
        )

    for node in sorted(extra, key=lambda n: (n.type_name, n.node_id)):
        if node in covered_extra:
            continue
        kind = _kind_from_desired_node(node)
        name = _display_name_for_node(node)
        updated.append(
            EntityStatus(
                kind=kind,
                name=name,
                path=None,
                markdown="ok",
                issues=(),
                registry="extra",
                node=node,
            )
        )
    return updated


def _kind_from_desired_node(node: DesiredNode) -> EntityKind:
    if node.type_name == "work_package":
        return "work_package"
    if node.type_name == "initiative":
        return "initiative"
    if node.type_name == "project":
        return "project"
    if node.type_name == "milestone":
        return "milestone"
    return "goal"


def _display_name_for_node(node: DesiredNode) -> str:
    if node.type_name == "work_package":
        # project/{project}/{slug} → project/slug
        parts = node.node_id.split("/")
        if len(parts) >= 3:
            return f"{parts[1]}/{parts[-1]}"
    return natural_name_from_node_id(node.node_id)
