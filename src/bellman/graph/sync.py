"""Sync roadmap model to pyfits graph."""

from __future__ import annotations

from pathlib import Path

from pyfits import CreatedObject, Id, InstanceName, ObjectTypeName, Repo, ValidateResult
from pyfits._native import load_library
from pyfits.errors import FitsError
from pyfits.models import Graph
from pyfits.result import Err, Ok, Result

from bellman import layout
from bellman.graph import link_naming
from bellman.graph.desired import (
    desired_node_ids,
    entity_node_id,
    flatten_wps,
    goal_node_id,
    milestone_node_id,
    resolve_entity_ref_from_layout,
    resolve_scope_ref,
    resolve_wp_ref,
    scope_node_id,
    wp_node_id,
)
from bellman.graph.fits_errors import (
    ignore_duplicate_instance,
    ignore_duplicate_link,
    ignore_nothing_to_remove,
    is_already_exists,
)
from bellman.graph.history import BellmanHistoryError
from bellman.graph.identity import InstanceIndex
from bellman.graph.legacy import is_legacy_flat_node_id
from bellman.graph.links_file import reconcile_link_artifacts
from bellman.graph.registry import bootstrap_registry
from bellman.model import Goal, Initiative, Milestone, Project, Roadmap
from bellman.parse.goal import parse_goal
from bellman.parse.milestone import parse_milestone
from bellman.parse.work_scope import parse_work_scope
from bellman.roadmap import load


def libfits_available() -> bool:
    """Return True when libfits can be loaded."""
    return isinstance(load_library(), Ok)


def _legacy_name_for_qualified(type_name: str, qualified_name: str) -> str | None:
    """Return the pre-migration flat name for a type-qualified node name."""
    prefix = f"{type_name}--"
    if not qualified_name.startswith(prefix):
        return None
    legacy_name = qualified_name[len(prefix) :]
    if is_legacy_flat_node_id(type_name, legacy_name):
        return legacy_name
    return None


def _migrate_legacy_node_ids(
    repo: Repo,
    root: Path,
    desired: set[str],
) -> Result[None, FitsError]:
    """Rename legacy flat node names to type-qualified names before ensure/prune."""
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Ok(None)
    index = index_result.ok_value
    live_node_names = index.live_node_names()

    for inst in index.by_name.values():
        if inst.kind != "node":
            continue
        if not is_legacy_flat_node_id(inst.type_name, inst.instance_name):
            continue
        legacy_name = inst.instance_name
        qualified_name = entity_node_id(inst.type_name, legacy_name)
        if qualified_name not in desired:
            continue

        if qualified_name in live_node_names:
            removed = ignore_nothing_to_remove(repo.remove(Id(inst.guid)))
            if isinstance(removed, Err):
                return removed
            live_node_names.discard(legacy_name)
            continue

        renamed = repo.rename_instance(
            guid=Id(inst.guid),
            new_name=InstanceName(qualified_name),
        )
        if isinstance(renamed, Err):
            return renamed
        live_node_names.discard(legacy_name)
        live_node_names.add(qualified_name)

    return Ok(None)


def _logical_scope_name(scope: Initiative | Project) -> str:
    return scope_node_id(scope)


def _logical_wp_name(project_name: str, slug: str) -> str:
    return wp_node_id(project_name, slug)


def _logical_milestone_name(name: str) -> str:
    return milestone_node_id(name)


def _logical_goal_name(name: str) -> str:
    return goal_node_id(name)


def _reload_graph(repo: Repo) -> Result[Graph, FitsError]:
    """Refresh the in-memory graph snapshot from the repository."""
    return repo.output_graph()


def _desired_graph_node_names(roadmap: Roadmap) -> set[str]:
    """Logical node names that should exist after a full roadmap sync."""
    return desired_node_ids(roadmap)


def _history_to_fits_error(err: BellmanHistoryError) -> FitsError:
    return FitsError(err.format(), code="history_load_failed")


def _prune_stale_registry(
    repo: Repo,
    root: Path,
    desired: set[str],
) -> Result[None, FitsError]:
    """Remove live registry node instances whose logical name is not in ``desired``."""
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Ok(None)
    for inst in index_result.ok_value.by_name.values():
        if inst.kind != "node" or inst.instance_name in desired:
            continue
        removed = ignore_nothing_to_remove(repo.remove(Id(inst.guid)))
        if isinstance(removed, Err):
            return removed
    return Ok(None)


def _prune_stale_graph(
    repo: Repo,
    root: Path,
    graph: Graph,
    desired: set[str],
) -> Result[Graph, FitsError]:
    """Remove stale links and nodes from the registry and graph snapshot."""
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(_history_to_fits_error(index_result.err_value))
    index = index_result.ok_value

    stale_edges = [
        edge
        for edge in graph.edges
        if (index.name_for_guid(edge.from_id.value) or "") not in desired
        or (index.name_for_guid(edge.to_id.value) or "") not in desired
    ]
    for edge in stale_edges:
        link_id = edge.id
        if link_id is None:
            continue
        removed = ignore_nothing_to_remove(repo.remove(link_id))
        if isinstance(removed, Err):
            return removed
    if stale_edges:
        reloaded = _reload_graph(repo)
        if isinstance(reloaded, Err):
            return reloaded
        graph = reloaded.ok_value

    stale_nodes = [
        node
        for node in graph.nodes
        if (index.name_for_guid(node.id.value) or "") not in desired
    ]
    stale_logical_names = {
        name
        for node in stale_nodes
        if (name := index.name_for_guid(node.id.value)) is not None
    }
    if stale_logical_names:
        reconciled = reconcile_link_artifacts(
            root,
            drop_touching_nodes=stale_logical_names,
        )
        if isinstance(reconciled, Err):
            return reconciled

    for node in stale_nodes:
        removed = ignore_nothing_to_remove(repo.remove(node.id))
        if isinstance(removed, Err):
            return removed

    registry_pruned = _prune_stale_registry(repo, root, desired)
    if isinstance(registry_pruned, Err):
        return registry_pruned

    repaired = reconcile_link_artifacts(root)
    if isinstance(repaired, Err):
        return repaired

    if stale_nodes or stale_edges:
        reloaded = _reload_graph(repo)
        if isinstance(reloaded, Err):
            return reloaded
        return Ok(reloaded.ok_value)
    return Ok(graph)


_ENTITY_KIND_TO_TYPE = {
    "initiative": "initiative",
    "archived-initiative": "initiative",
    "project": "project",
    "milestone": "milestone",
    "goal": "goal",
}


def _deleted_node_names(kind: str, name: str, root: Path) -> set[str]:
    """Return logical node names to remove after deleting a layout entity."""
    type_name = _ENTITY_KIND_TO_TYPE.get(kind)
    if type_name is None:
        msg = f"unknown entity kind {kind!r}"
        raise ValueError(msg)

    names: set[str] = {entity_node_id(type_name, name), name}
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Ok) and kind == "project":
        prefix = f"{name}--"
        for inst in index_result.ok_value.by_name.values():
            if inst.kind == "node" and inst.instance_name.startswith(prefix):
                names.add(inst.instance_name)
    return names


def _rename_graph_kind(kind: str) -> str:
    if kind == "archived-initiative":
        return "initiative"
    return kind


def _validate_graph(repo: Repo, root: Path) -> Result[ValidateResult, FitsError]:
    """Validate the repository after reconciling link artifacts."""
    repaired = reconcile_link_artifacts(root)
    if isinstance(repaired, Err):
        return repaired
    return repo.validate()


def prune_deleted_entity(
    root: Path,
    kind: str,
    name: str,
) -> Result[None, FitsError]:
    """Remove a deleted layout entity from the pyfits graph without full roadmap load.

    Args:
        root: Roadmap root directory.
        kind: Entity kind from :func:`bellman.layout.delete_entity`
            (e.g. ``initiative``, ``project``, ``goal``).
        name: Natural entity name (kebab-case).

    Returns:
        ``Ok(None)`` when pruning and libfits validation succeed.
        ``Err(FitsError)`` when libfits is unavailable, the repo is not
        initialized, or pruning fails.
    """
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    if not (root / ".fits").is_dir():
        return Err(
            FitsError(
                "Roadmap not initialized; run bellman init",
                code="not_initialized",
            )
        )

    try:
        node_names = _deleted_node_names(kind, name, root)
    except ValueError as exc:
        return Err(FitsError(str(exc), code="invalid_entity"))

    reconciled = reconcile_link_artifacts(root, drop_touching_nodes=node_names)
    if isinstance(reconciled, Err):
        return reconciled

    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(_history_to_fits_error(index_result.err_value))
    index = index_result.ok_value

    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        boot = bootstrap_registry(repo)
        if isinstance(boot, Err):
            return boot

        for logical_name in node_names:
            guid = index.guid_for_name(logical_name)
            if guid is None:
                continue
            removed = ignore_nothing_to_remove(repo.remove(guid))
            if isinstance(removed, Err):
                return removed

        val = _validate_graph(repo, root)
        if isinstance(val, Err):
            return val
    return Ok(None)


_CREATE_ENTITY_KINDS = frozenset({"initiative", "project", "milestone", "goal"})


def _parse_created_entity(
    root: Path,
    kind: str,
    name: str,
) -> Result[Initiative | Project | Milestone | Goal, FitsError]:
    """Parse a single layout entity file for targeted graph sync."""
    try:
        if kind == "initiative":
            path = layout.initiative_path(root, name)
            initiative = parse_work_scope(path, is_project=False)
            assert isinstance(initiative, Initiative)
            return Ok(initiative)
        if kind == "project":
            path = layout.project_md_path(root, name)
            wp_path = layout.work_packages_path(root, name)
            project = parse_work_scope(
                path,
                is_project=True,
                work_packages_path=wp_path,
            )
            assert isinstance(project, Project)
            return Ok(project)
        if kind == "milestone":
            return Ok(parse_milestone(layout.milestone_path(root, name)))
        if kind == "goal":
            return Ok(parse_goal(layout.goal_path(root, name)))
        msg = f"unknown entity kind {kind!r}"
        raise ValueError(msg)
    except (ValueError, OSError) as exc:
        return Err(FitsError(str(exc), code="entity_load_failed"))


def _sync_scope_dependencies_layout(
    repo: Repo,
    root: Path,
    graph: Graph,
    scope: Initiative | Project,
) -> Result[None, FitsError]:
    """Ensure scope dependency links using filesystem entity resolution."""
    sid = _logical_scope_name(scope)
    try:
        for edge in scope.dependencies:
            pred = resolve_entity_ref_from_layout(root, edge.predecessor)
            lt = f"{link_naming.precedes_link_type(edge.relation, edge.hardness)}_scope"
            link_name = link_naming.wire_link_name(lt, pred, sid)
            link_res = _ensure_link(
                repo,
                root,
                graph,
                link_type=lt,
                from_logical=pred,
                to_logical=sid,
                link_name=link_name,
            )
            if isinstance(link_res, Err):
                return link_res
    except ValueError as exc:
        return Err(FitsError(str(exc), code="entity_load_failed"))
    return Ok(None)


def sync_renamed_entity(
    root: Path,
    kind: str,
    old_name: str,
    new_name: str,
) -> Result[None, FitsError]:
    """Rename layout entity instances in pyfits and refresh dependency links.

    Args:
        root: Roadmap root directory.
        kind: Entity kind from :func:`bellman.layout.rename_entity`.
        old_name: Previous natural entity name (kebab-case).
        new_name: New natural entity name (kebab-case).

    Returns:
        ``Ok(None)`` when renames and validation succeed.
        ``Err(FitsError)`` when libfits is unavailable, the repo is not
        initialized, or sync fails.
    """
    type_name = _ENTITY_KIND_TO_TYPE.get(kind)
    if type_name is None:
        return Err(FitsError(f"unknown entity kind {kind!r}", code="invalid_entity"))
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    if not (root / ".fits").is_dir():
        return Err(
            FitsError(
                "Roadmap not initialized; run bellman init",
                code="not_initialized",
            )
        )

    renames: list[tuple[str, str]] = [
        (entity_node_id(type_name, old_name), entity_node_id(type_name, new_name)),
        (old_name, entity_node_id(type_name, new_name)),
    ]
    if kind == "project":
        renames.extend(_project_wp_node_renames(root, old_name, new_name))

    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        boot = bootstrap_registry(repo)
        if isinstance(boot, Err):
            return boot

        index_result = InstanceIndex.load(root)
        if isinstance(index_result, Err):
            return Err(_history_to_fits_error(index_result.err_value))
        index = index_result.ok_value
        live_node_names = index.live_node_names()

        seen_old: set[str] = set()
        for old_logical, new_logical in renames:
            if old_logical in seen_old or old_logical == new_logical:
                continue
            seen_old.add(old_logical)
            if old_logical not in live_node_names:
                continue
            guid = index.guid_for_name(old_logical)
            if guid is None:
                continue
            renamed = repo.rename_instance(
                guid=guid,
                new_name=InstanceName(new_logical),
            )
            if isinstance(renamed, Err):
                return renamed
            live_node_names.discard(old_logical)
            live_node_names.add(new_logical)

        sync_kind = _rename_graph_kind(kind)
        if kind in _CREATE_ENTITY_KINDS:
            resync = sync_created_entity(root, sync_kind, new_name)
            if isinstance(resync, Err):
                return resync

        val = _validate_graph(repo, root)
        if isinstance(val, Err):
            return val
    return Ok(None)


def _project_wp_node_renames(
    root: Path,
    old_name: str,
    new_name: str,
) -> list[tuple[str, str]]:
    """Return work-package logical name renames after a project rename."""
    renames: list[tuple[str, str]] = []
    wp_path = layout.work_packages_path(root, new_name)
    if wp_path.is_file():
        try:
            project = parse_work_scope(
                layout.project_md_path(root, new_name),
                is_project=True,
                work_packages_path=wp_path,
            )
            assert isinstance(project, Project)
            for wp, _parent in flatten_wps(project.work_packages, None, project.name):
                renames.append(
                    (
                        wp_node_id(old_name, wp.slug),
                        wp_node_id(new_name, wp.slug),
                    )
                )
        except (ValueError, OSError):
            pass

    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Ok):
        prefix = f"{old_name}--"
        known_old = {old for old, _new in renames}
        for inst in index_result.ok_value.by_name.values():
            if inst.kind != "node" or not inst.instance_name.startswith(prefix):
                continue
            if inst.instance_name in known_old:
                continue
            slug = inst.instance_name[len(prefix) :]
            renames.append((inst.instance_name, wp_node_id(new_name, slug)))
    return renames


def sync_created_entity(
    root: Path,
    kind: str,
    name: str,
) -> Result[None, FitsError]:
    """Register a newly created layout entity in pyfits without full roadmap load.

    Args:
        root: Roadmap root directory.
        kind: Entity kind (``initiative``, ``project``, ``milestone``, ``goal``).
        name: Natural entity name (kebab-case).

    Returns:
        ``Ok(None)`` when the entity is registered and validation succeeds.
        ``Err(FitsError)`` when libfits is unavailable, the repo is not
        initialized, the entity file fails to parse, or sync fails.
    """
    if kind not in _CREATE_ENTITY_KINDS:
        return Err(FitsError(f"unknown entity kind {kind!r}", code="invalid_entity"))
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    if not (root / ".fits").is_dir():
        return Err(
            FitsError(
                "Roadmap not initialized; run bellman init",
                code="not_initialized",
            )
        )

    parsed = _parse_created_entity(root, kind, name)
    if isinstance(parsed, Err):
        return parsed
    entity = parsed.ok_value

    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        boot = bootstrap_registry(repo)
        if isinstance(boot, Err):
            return boot
        graph_result = repo.output_graph()
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value

        if kind == "initiative":
            initiative = entity
            assert isinstance(initiative, Initiative)
            ensured = _ensure_node(
                repo,
                root,
                graph,
                type_name="initiative",
                logical_name=_logical_scope_name(initiative),
                title=initiative.title,
            )
            if isinstance(ensured, Err):
                return ensured
            dep_sync = _sync_scope_dependencies_layout(repo, root, graph, initiative)
            if isinstance(dep_sync, Err):
                return dep_sync
        elif kind == "project":
            project = entity
            assert isinstance(project, Project)
            ensured = _ensure_node(
                repo,
                root,
                graph,
                type_name="project",
                logical_name=_logical_scope_name(project),
                title=project.title,
            )
            if isinstance(ensured, Err):
                return ensured
            wp_sync = _sync_project_wps(repo, root, graph, project)
            if isinstance(wp_sync, Err):
                return wp_sync
            dep_sync = _sync_scope_dependencies_layout(repo, root, graph, project)
            if isinstance(dep_sync, Err):
                return dep_sync
        elif kind == "milestone":
            milestone = entity
            assert isinstance(milestone, Milestone)
            ensured = _ensure_node(
                repo,
                root,
                graph,
                type_name="milestone",
                logical_name=_logical_milestone_name(milestone.name),
                title=milestone.title,
            )
            if isinstance(ensured, Err):
                return ensured
        else:
            goal = entity
            assert isinstance(goal, Goal)
            ensured = _ensure_node(
                repo,
                root,
                graph,
                type_name="goal",
                logical_name=_logical_goal_name(goal.name),
                title=goal.title,
            )
            if isinstance(ensured, Err):
                return ensured

        val = _validate_graph(repo, root)
        if isinstance(val, Err):
            return val
    return Ok(None)


def _ensure_node(
    repo: Repo,
    root: Path,
    graph: Graph,
    *,
    type_name: str,
    logical_name: str,
    title: str,
) -> Result[CreatedObject, FitsError]:
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(_history_to_fits_error(index_result.err_value))
    index = index_result.ok_value

    if logical_name in index.live_node_names():
        existing = index.by_name[logical_name]
        return Ok(CreatedObject(guid=Id(existing.guid), name=logical_name))

    legacy_name = _legacy_name_for_qualified(type_name, logical_name)
    if legacy_name is not None and legacy_name in index.live_node_names():
        legacy = index.by_name[legacy_name]
        renamed = repo.rename_instance(
            guid=Id(legacy.guid),
            new_name=InstanceName(logical_name),
        )
        if isinstance(renamed, Ok):
            return renamed
        if isinstance(renamed, Err) and not is_already_exists(renamed.err_value):
            return renamed

    result = repo.new_node(
        ObjectTypeName(type_name),
        name=InstanceName(logical_name),
        title=title,
    )
    return ignore_duplicate_instance(
        result,
        logical_name=logical_name,
        guid=index.guid_for_name(logical_name),
    )


def _ensure_link(
    repo: Repo,
    root: Path,
    graph: Graph,
    *,
    link_type: str,
    from_logical: str,
    to_logical: str,
    link_name: InstanceName,
) -> Result[CreatedObject, FitsError]:
    index_result = InstanceIndex.load(root)
    if isinstance(index_result, Err):
        return Err(_history_to_fits_error(index_result.err_value))
    index = index_result.ok_value

    in_guid = index.guid_for_name(from_logical)
    out_guid = index.guid_for_name(to_logical)
    if in_guid is None:
        return Err(
            FitsError(
                f"link endpoint not registered: {from_logical!r}",
                code="endpoint_not_found",
            )
        )
    if out_guid is None:
        return Err(
            FitsError(
                f"link endpoint not registered: {to_logical!r}",
                code="endpoint_not_found",
            )
        )

    for edge in graph.edges:
        if (
            edge.link_type == link_type
            and edge.from_id == in_guid
            and edge.to_id == out_guid
        ):
            edge_guid = edge.id
            if edge_guid is not None:
                return Ok(CreatedObject(guid=edge_guid, name=link_name.value))

    result = repo.new_link(link_type, in_guid, out_guid, name=link_name)
    existing_guid = index.guid_for_name(link_name.value)
    return ignore_duplicate_link(
        result,
        link_name=link_name.value,
        guid=existing_guid,
    )


def _sync_project_wps(
    repo: Repo,
    root: Path,
    graph: Graph,
    project: Project,
) -> Result[None, FitsError]:
    flat = flatten_wps(project.work_packages, None, project.name)
    for wp, parent in flat:
        wid = _logical_wp_name(project.name, wp.slug)
        created = _ensure_node(
            repo,
            root,
            graph,
            type_name="work_package",
            logical_name=wid,
            title=wp.title,
        )
        if isinstance(created, Err):
            return created
        if parent is not None:
            parent_name = _logical_wp_name(project.name, parent.slug)
            plink = _ensure_link(
                repo,
                root,
                graph,
                link_type="parent_of",
                from_logical=parent_name,
                to_logical=wid,
                link_name=link_naming.wire_link_name("parent_of", parent_name, wid),
            )
            if isinstance(plink, Err):
                return plink
        for edge in wp.dependencies:
            pred = resolve_wp_ref(project.name, edge.predecessor)
            lt = link_naming.precedes_link_type(edge.relation, edge.hardness)
            link_name = link_naming.wire_link_name(lt, pred, wid)
            link_res = _ensure_link(
                repo,
                root,
                graph,
                link_type=lt,
                from_logical=pred,
                to_logical=wid,
                link_name=link_name,
            )
            if isinstance(link_res, Err):
                return link_res
    return Ok(None)


def _sync_scope_dependencies(
    repo: Repo,
    root: Path,
    graph: Graph,
    roadmap: Roadmap,
    scope: Initiative | Project,
) -> Result[None, FitsError]:
    sid = _logical_scope_name(scope)

    for edge in scope.dependencies:
        pred = resolve_scope_ref(roadmap, edge.predecessor)
        lt = f"{link_naming.precedes_link_type(edge.relation, edge.hardness)}_scope"
        link_name = link_naming.wire_link_name(lt, pred, sid)
        link_res = _ensure_link(
            repo,
            root,
            graph,
            link_type=lt,
            from_logical=pred,
            to_logical=sid,
            link_name=link_name,
        )
        if isinstance(link_res, Err):
            return link_res
    return Ok(None)


def init_pyfits_repo(root: Path) -> Result[None, FitsError]:
    """Initialize pyfits repository scaffolding at ``root``.

    Creates ``.fits/``, graph roots, and registers bellman types when missing.
    Idempotent when the repository is already initialized.

    Args:
        root: Roadmap root directory.

    Returns:
        ``Ok(None)`` when initialization succeeds or was already done.
        ``Err(FitsError)`` when libfits is unavailable or initialization fails.
    """
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        if not (root / ".fits").is_dir():
            init_res = repo.init()
            if isinstance(init_res, Err):
                return init_res
        boot = bootstrap_registry(repo)
        if isinstance(boot, Err):
            return boot
    return Ok(None)


def sync_roadmap(
    root: Path,
    *,
    prune: bool = False,
) -> Result[None, FitsError]:
    """Load roadmap and sync nodes/links into pyfits repository at ``root``.

    Requires an initialized pyfits repository (``bellman init``). Does not create
    ``.fits/``, ``nodes/``, or ``links/``.

    Args:
        root: Roadmap root directory.
        prune: When True, remove graph objects no longer present in markdown.

    Returns:
        ``Ok(None)`` when sync and libfits validation succeed.
        ``Err(FitsError)`` when libfits is unavailable, the repo is not
        initialized, roadmap load fails, or sync/validation fails.
    """
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    if not (root / ".fits").is_dir():
        return Err(
            FitsError(
                "Roadmap not initialized; run bellman init",
                code="not_initialized",
            )
        )
    try:
        roadmap = load(root)
    except (ValueError, OSError) as exc:
        return Err(FitsError(str(exc), code="roadmap_load_failed"))
    open_result = Repo.open(root)
    if isinstance(open_result, Err):
        return open_result
    repo = open_result.ok_value
    with repo:
        boot = bootstrap_registry(repo)
        if isinstance(boot, Err):
            return boot
        graph_result = repo.output_graph()
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value
        desired = _desired_graph_node_names(roadmap)
        migrated = _migrate_legacy_node_ids(repo, root, desired)
        if isinstance(migrated, Err):
            return migrated
        graph_result = repo.output_graph()
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value

        for initiative in roadmap.initiatives:
            res = _ensure_node(
                repo,
                root,
                graph,
                type_name="initiative",
                logical_name=_logical_scope_name(initiative),
                title=initiative.title,
            )
            if isinstance(res, Err):
                return res

        for archived in roadmap.archived_initiatives:
            if roadmap.project_by_name(archived.name) is not None:
                continue
            res = _ensure_node(
                repo,
                root,
                graph,
                type_name="initiative",
                logical_name=_logical_scope_name(archived),
                title=archived.title,
            )
            if isinstance(res, Err):
                return res

        for project in roadmap.projects:
            if layout.archived_initiative_path(root, project.name).exists():
                index_result = InstanceIndex.load(root)
                if isinstance(index_result, Ok):
                    init_logical = entity_node_id("initiative", project.name)
                    init_guid = index_result.ok_value.guid_for_name(init_logical)
                    if init_guid is not None:
                        removed = repo.remove(init_guid)
                        if isinstance(removed, Err):
                            return removed
                        reloaded = _reload_graph(repo)
                        if isinstance(reloaded, Err):
                            return reloaded
                        graph = reloaded.ok_value
            res = _ensure_node(
                repo,
                root,
                graph,
                type_name="project",
                logical_name=_logical_scope_name(project),
                title=project.title,
            )
            if isinstance(res, Err):
                return res
            wp_sync = _sync_project_wps(repo, root, graph, project)
            if isinstance(wp_sync, Err):
                return wp_sync

        for milestone in roadmap.milestones:
            res = _ensure_node(
                repo,
                root,
                graph,
                type_name="milestone",
                logical_name=_logical_milestone_name(milestone.name),
                title=milestone.title,
            )
            if isinstance(res, Err):
                return res

        for goal in roadmap.goals:
            res = _ensure_node(
                repo,
                root,
                graph,
                type_name="goal",
                logical_name=_logical_goal_name(goal.name),
                title=goal.title,
            )
            if isinstance(res, Err):
                return res

        for scope in roadmap.all_work_scopes():
            dep_sync = _sync_scope_dependencies(repo, root, graph, roadmap, scope)
            if isinstance(dep_sync, Err):
                return dep_sync

        if prune:
            pruned = _prune_stale_graph(repo, root, graph, desired)
            if isinstance(pruned, Err):
                return pruned
            graph = pruned.ok_value

        val = _validate_graph(repo, root)
        if isinstance(val, Err):
            return val
    return Ok(None)
