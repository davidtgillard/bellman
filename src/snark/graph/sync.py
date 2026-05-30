"""Sync roadmap model to pyfits graph."""

from __future__ import annotations

from pathlib import Path

from pyfits import Id, ObjectTypeName, Repo, TargetId
from pyfits._native import load_library
from pyfits.errors import FitsError
from pyfits.models import Graph
from pyfits.result import Err, Ok, Result

from snark import layout
from snark.graph import link_naming
from snark.graph.fits_errors import ignore_duplicate_instance, ignore_duplicate_link
from snark.graph.registry import bootstrap_registry
from snark.model import Initiative, Project, Roadmap, WorkPackage
from snark.roadmap import load


def libfits_available() -> bool:
    """Return True when libfits can be loaded."""
    return isinstance(load_library(), Ok)


def _scope_node_id(scope: Initiative | Project) -> Id:
    """Flat node id (opaque target_id); type is in the registry."""
    return Id(scope.name)


def _wp_node_id(project_name: str, slug: str) -> Id:
    return Id(f"{project_name}--{slug}")


def _milestone_node_id(name: str) -> Id:
    return Id(name)


def _goal_node_id(name: str) -> Id:
    return Id(name)


def _graph_node_ids(graph: Graph) -> set[str]:
    return {n.id.value for n in graph.nodes}


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
    slug = ref.split("/", 1)[-1] if "/" in ref else ref
    return _wp_node_id(project_name, slug)


def _flatten_wps(
    packages: tuple[WorkPackage, ...],
    parent: WorkPackage | None,
    project_name: str,
) -> list[tuple[WorkPackage, WorkPackage | None]]:
    out: list[tuple[WorkPackage, WorkPackage | None]] = []
    for wp in packages:
        out.append((wp, parent))
        out.extend(_flatten_wps(wp.children, wp, project_name))
    return out


def _sync_project_wps(
    repo: Repo,
    graph: Graph,
    project: Project,
) -> Result[None, FitsError]:
    flat = _flatten_wps(project.work_packages, None, project.name)
    for wp, parent in flat:
        wid = _wp_node_id(project.name, wp.slug)
        created = _ensure_node(
            repo,
            graph,
            type_name="work_package",
            node_id=wid,
            title=wp.slug,
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
        for initiative in (*roadmap.initiatives, *roadmap.archived_initiatives):
            if initiative.name == ref:
                return _scope_node_id(initiative)
        proj = roadmap.project_by_name(ref)
        if proj is not None:
            return _scope_node_id(proj)
        return Id(ref)

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


def sync_roadmap(
    root: Path,
    *,
    prune: bool = False,
) -> Result[None, FitsError]:
    """Load roadmap and sync nodes/links into pyfits repository at ``root``."""
    _ = prune
    if not libfits_available():
        return Err(
            FitsError(
                "libfits not available; set PYFITS_LIB_PATH or build ../fits",
                code="lib_not_found",
            )
        )
    roadmap = load(root)
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
        graph_result = repo.output_graph()
        if isinstance(graph_result, Err):
            return graph_result
        graph = graph_result.ok_value

        for initiative in (*roadmap.initiatives, *roadmap.archived_initiatives):
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

        for project in roadmap.projects:
            pid = _scope_node_id(project)
            res = _ensure_node(
                repo,
                graph,
                type_name="project",
                node_id=pid,
                title=project.title,
            )
            if isinstance(res, Err):
                return res
            if layout.archived_initiative_path(root, project.name).exists():
                iid = Id(project.name)
                promo = _ensure_link(
                    repo,
                    graph,
                    link_type="promoted_from",
                    in_id=pid,
                    out_id=iid,
                    target_id=link_naming.wire_target_id(
                        "promoted_from", pid.value, iid.value
                    ),
                )
                if isinstance(promo, Err):
                    return promo
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

        val = repo.validate()
        if isinstance(val, Err):
            return val
    return Ok(None)
