"""Sync roadmap model to pyfits graph."""

from __future__ import annotations

from pathlib import Path

from pyfits import Id, ObjectTypeName, Repo, TargetId
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
    resolve_scope_ref,
    resolve_wp_ref,
    scope_node_id,
    wp_node_id,
)
from bellman.graph.fits_errors import ignore_duplicate_instance, ignore_duplicate_link
from bellman.graph.history import load_graph_history
from bellman.graph.registry import bootstrap_registry
from bellman.model import Initiative, Project, Roadmap
from bellman.roadmap import load


def libfits_available() -> bool:
    """Return True when libfits can be loaded."""
    return isinstance(load_library(), Ok)


def _scope_node_id(scope: Initiative | Project) -> Id:
    return Id(scope_node_id(scope))


def _wp_node_id(project_name: str, slug: str) -> Id:
    return Id(wp_node_id(project_name, slug))


def _milestone_node_id(name: str) -> Id:
    return Id(milestone_node_id(name))


def _goal_node_id(name: str) -> Id:
    return Id(goal_node_id(name))


def _graph_node_ids(graph: Graph) -> set[str]:
    return {n.id.value for n in graph.nodes}


def _reload_graph(repo: Repo) -> Result[Graph, FitsError]:
    """Refresh the in-memory graph snapshot from the repository."""
    return repo.output_graph()


def _desired_graph_node_ids(roadmap: Roadmap) -> set[str]:
    """Opaque node ids that should exist after a full roadmap sync."""
    return desired_node_ids(roadmap)


def _prune_stale_registry(
    repo: Repo,
    root: Path,
    desired: set[str],
) -> Result[None, FitsError]:
    """Remove live registry instances whose opaque id is not in ``desired``."""
    history_result = load_graph_history(root)
    if isinstance(history_result, Err):
        return Ok(None)
    for inst in history_result.ok_value.instances:
        if inst.kind != "node" or inst.instance_id in desired:
            continue
        removed = repo.remove(Id(inst.instance_id))
        if isinstance(removed, Err):
            return removed
    return Ok(None)


def _prune_stale_graph(
    repo: Repo,
    root: Path,
    graph: Graph,
    desired: set[str],
) -> Result[Graph, FitsError]:
    """Remove stale nodes from the registry and graph snapshot."""
    pruned = _prune_stale_registry(repo, root, desired)
    if isinstance(pruned, Err):
        return pruned
    reloaded = _reload_graph(repo)
    if isinstance(reloaded, Err):
        return reloaded
    graph = reloaded.ok_value
    stale_nodes = [n for n in graph.nodes if n.id.value not in desired]
    for node in stale_nodes:
        removed = repo.remove(node.id)
        if isinstance(removed, Err):
            return removed
    if stale_nodes:
        reloaded = _reload_graph(repo)
        if isinstance(reloaded, Err):
            return reloaded
        graph = reloaded.ok_value
    stale_edges = [
        edge
        for edge in graph.edges
        if edge.from_id.value not in desired or edge.to_id.value not in desired
    ]
    for edge in stale_edges:
        link_id = edge.id
        if link_id is None:
            continue
        removed = repo.remove(link_id)
        if isinstance(removed, Err):
            return removed
    if stale_edges:
        reloaded = _reload_graph(repo)
        if isinstance(reloaded, Err):
            return reloaded
        return Ok(reloaded.ok_value)
    return Ok(graph)


def _ensure_node(
    repo: Repo,
    graph: Graph,
    *,
    type_name: str,
    node_id: Id,
    title: str,
) -> Result[Id, FitsError]:
    if node_id.value in _graph_node_ids(graph):
        return Ok(node_id)
    result = repo.new_node(
        ObjectTypeName(type_name),
        target_id=TargetId.parse(node_id.value),
        title=title,
    )
    if isinstance(result, Ok):
        graph = Graph(
            nodes=[*graph.nodes],
            edges=graph.edges,
        )
    return ignore_duplicate_instance(result, node_id=node_id)


def _ensure_link(
    repo: Repo,
    graph: Graph,
    *,
    link_type: str,
    in_id: Id,
    out_id: Id,
    target_id: TargetId,
) -> Result[Id, FitsError]:
    for edge in graph.edges:
        if (
            edge.link_type == link_type
            and edge.from_id == in_id
            and edge.to_id == out_id
        ):
            return Ok(edge.id or Id(target_id.value))
    return ignore_duplicate_link(
        repo.new_link(link_type, in_id, out_id, target_id=target_id),
        link_id=Id(target_id.value),
    )


def _resolve_wp_ref(project_name: str, ref: str) -> Id:
    return Id(resolve_wp_ref(project_name, ref))


def _sync_project_wps(
    repo: Repo,
    graph: Graph,
    project: Project,
) -> Result[None, FitsError]:
    flat = flatten_wps(project.work_packages, None, project.name)
    for wp, parent in flat:
        wid = _wp_node_id(project.name, wp.slug)
        created = _ensure_node(
            repo,
            graph,
            type_name="work_package",
            node_id=wid,
            title=wp.title,
        )
        if isinstance(created, Err):
            return created
        if parent is not None:
            parent_id = _wp_node_id(project.name, parent.slug)
            plink = _ensure_link(
                repo,
                graph,
                link_type="parent_of",
                in_id=parent_id,
                out_id=wid,
                target_id=link_naming.wire_target_id(
                    "parent_of", parent_id.value, wid.value
                ),
            )
            if isinstance(plink, Err):
                return plink
        for edge in wp.dependencies:
            pred = _resolve_wp_ref(project.name, edge.predecessor)
            lt = link_naming.precedes_link_type(edge.relation, edge.hardness)
            tid = link_naming.wire_target_id(lt, pred.value, wid.value)
            link_res = _ensure_link(
                repo,
                graph,
                link_type=lt,
                in_id=pred,
                out_id=wid,
                target_id=tid,
            )
            if isinstance(link_res, Err):
                return link_res
    return Ok(None)


def _sync_scope_dependencies(
    repo: Repo,
    graph: Graph,
    roadmap: Roadmap,
    scope: Initiative | Project,
) -> Result[None, FitsError]:
    sid = _scope_node_id(scope)

    def resolve_scope(ref: str) -> Id:
        return Id(resolve_scope_ref(roadmap, ref))

    for edge in scope.dependencies:
        pred = resolve_scope(edge.predecessor)
        lt = f"{link_naming.precedes_link_type(edge.relation, edge.hardness)}_scope"
        tid = link_naming.wire_target_id(lt, pred.value, sid.value)
        link_res = _ensure_link(
            repo,
            graph,
            link_type=lt,
            in_id=pred,
            out_id=sid,
            target_id=tid,
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
        initialized, or sync/validation fails.
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
    roadmap = load(root)
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

        for initiative in roadmap.initiatives:
            nid = _scope_node_id(initiative)
            res = _ensure_node(
                repo,
                graph,
                type_name="initiative",
                node_id=nid,
                title=initiative.title,
            )
            if isinstance(res, Err):
                return res

        for archived in roadmap.archived_initiatives:
            if roadmap.project_by_name(archived.name) is not None:
                continue
            nid = _scope_node_id(archived)
            res = _ensure_node(
                repo,
                graph,
                type_name="initiative",
                node_id=nid,
                title=archived.title,
            )
            if isinstance(res, Err):
                return res

        for project in roadmap.projects:
            pid = _scope_node_id(project)
            if layout.archived_initiative_path(root, project.name).exists():
                init_id = Id(entity_node_id("initiative", project.name))
                removed = repo.remove(init_id)
                if isinstance(removed, Err):
                    return removed
                reloaded = _reload_graph(repo)
                if isinstance(reloaded, Err):
                    return reloaded
                graph = reloaded.ok_value
            res = _ensure_node(
                repo,
                graph,
                type_name="project",
                node_id=pid,
                title=project.title,
            )
            if isinstance(res, Err):
                return res
            wp_sync = _sync_project_wps(repo, graph, project)
            if isinstance(wp_sync, Err):
                return wp_sync

        for milestone in roadmap.milestones:
            mid = _milestone_node_id(milestone.name)
            res = _ensure_node(
                repo,
                graph,
                type_name="milestone",
                node_id=mid,
                title=milestone.title,
            )
            if isinstance(res, Err):
                return res

        for goal in roadmap.goals:
            gid = _goal_node_id(goal.name)
            res = _ensure_node(
                repo,
                graph,
                type_name="goal",
                node_id=gid,
                title=goal.title,
            )
            if isinstance(res, Err):
                return res

        for scope in roadmap.all_work_scopes():
            dep_sync = _sync_scope_dependencies(repo, graph, roadmap, scope)
            if isinstance(dep_sync, Err):
                return dep_sync

        if prune:
            pruned = _prune_stale_graph(
                repo, root, graph, _desired_graph_node_ids(roadmap)
            )
            if isinstance(pruned, Err):
                return pruned
            graph = pruned.ok_value

        val = repo.validate()
        if isinstance(val, Err):
            return val
    return Ok(None)
