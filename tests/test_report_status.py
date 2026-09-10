"""Unit tests for roadmap status reporting."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pyfits.models import Graph
from pyfits.result import Ok

from bellman import layout
from bellman.graph.delta import RegistryDelta
from bellman.graph.desired import DesiredNode
from bellman.graph.history import GraphHistory
from bellman.graph.identity import InstanceIndex
from bellman.report.status import compute_roadmap_status, format_status_report

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def _write_goal(root: Path, name: str, content: str) -> None:
    goal_dir = root / "goals"
    goal_dir.mkdir(parents=True, exist_ok=True)
    (goal_dir / f"{name}.md").write_text(content, encoding="utf-8")


def _write_project_with_wp(root: Path, wp_content: str) -> None:
    project_dir = root / "projects" / "billing-redesign"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "billing-redesign.md").write_text(
        "# Billing Redesign\n\n"
        "## Introduction\n\nTBD.\n\n"
        "## Motivation\n\nTBD.\n\n"
        "## Detailed Description\n\nTBD.\n\n"
        "### Criteria for Success\n\nShip it.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    (project_dir / "work-packages.yaml").write_text(wp_content, encoding="utf-8")


def test_example_roadmap_status_entities_ok() -> None:
    result = compute_roadmap_status(EXAMPLES, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    names = {e.name for e in status.entities}
    assert "explore-ml-ranking" in names
    assert "billing-redesign" in names
    assert "billing-redesign/wp-invoicing" in names
    assert "ga-release" in names
    assert "reduce-churn" in names
    assert all(e.markdown == "ok" for e in status.entities)
    assert all(e.registry == "n/a" for e in status.entities)
    assert status.registry_error is not None


def test_invalid_goal_marked_invalid(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "reduce-churn", "# Wrong Title\n\nSome content.\n")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    goal = next(e for e in result.ok_value.entities if e.name == "reduce-churn")
    assert goal.markdown == "invalid"
    assert any("does not match name" in issue for issue in goal.issues)


def test_unparseable_goal_appears_as_unparsed(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "broken-goal", "no header\n")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    goal = next(e for e in result.ok_value.entities if e.name == "broken-goal")
    assert goal.markdown == "unparsed"
    assert goal.issues


def test_unknown_estimate_is_warning(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_project_with_wp(
        tmp_path,
        "version: 1\n\n"
        "work_packages:\n"
        "  - title: wp-foo\n"
        "    description: Description.\n"
        "    estimate: unknown\n",
    )
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    wp = next(e for e in result.ok_value.entities if e.name.endswith("/wp-foo"))
    assert wp.markdown == "warning"
    assert any("unknown estimate" in issue for issue in wp.issues)


def test_registry_missing_node_on_entity(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "manual-goal", "# Manual Goal\n\nAdded by hand.\n")
    (tmp_path / ".fits").mkdir()
    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(GraphHistory())),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_FakeRepo(graph=Graph(nodes=(), edges=()))),
        ),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    status = result.ok_value
    goal = next(e for e in status.entities if e.name == "manual-goal")
    assert goal.registry == "missing"
    assert status.registry is not None
    assert status.registry.missing_nodes == ("goal manual-goal",)

    buf = StringIO()
    format_status_report(status, buf)
    output = buf.getvalue()
    assert "registry: missing" in output
    assert "Missing nodes:" in output
    assert "goal manual-goal" in output


def test_global_name_overlap_issue(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "shared-name")
    layout.create_project(tmp_path, "shared-name")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    assert any("both named" in issue for issue in status.global_issues)
    initiative = next(e for e in status.entities if e.kind == "initiative")
    project = next(e for e in status.entities if e.kind == "project")
    # Overlap is global; entities themselves may still be markdown-ok.
    assert initiative.name == "shared-name"
    assert project.name == "shared-name"


def test_no_registry_sets_n_a(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    assert all(e.registry == "n/a" for e in status.entities)
    assert status.registry is None
    assert status.registry_error is not None


def test_soft_registry_skip_when_libfits_unavailable(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch("bellman.graph.delta.libfits_available", return_value=False):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    assert result.ok_value.registry is None
    assert result.ok_value.registry_error is not None
    assert "libfits" in result.ok_value.registry_error.lower()


def test_format_status_includes_summary(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "reduce-churn", "# Wrong Title\n\nContent.\n")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    buf = StringIO()
    format_status_report(result.ok_value, buf)
    output = buf.getvalue()
    assert "Roadmap:" in output
    assert "Goals" in output
    assert "invalid" in output
    assert "Summary:" in output


def test_extra_registry_node_appears_in_inventory(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    delta = RegistryDelta(
        missing_nodes=(),
        extra_nodes=("goal orphan-goal",),
        missing_links=(),
        extra_links=(),
        extra_node_ids=frozenset({DesiredNode("goal", "goal/orphan-goal")}),
        desired_node_count=0,
        actual_node_count=1,
    )
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Ok(delta),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    orphan = next(e for e in result.ok_value.entities if e.name == "orphan-goal")
    assert orphan.registry == "extra"
    assert orphan.kind == "goal"


def test_hard_registry_delta_error(tmp_path: Path) -> None:
    from pyfits.result import Err

    from bellman.graph.delta import RegistryDeltaError

    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Err(RegistryDeltaError("corrupt registry data")),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Err)
    assert "corrupt registry data" in result.err_value


def test_fits_error_from_registry_delta(tmp_path: Path) -> None:
    from pyfits.errors import FitsError
    from pyfits.result import Err

    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Err(FitsError("boom", code="test")),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Err)
    assert "boom" in result.err_value


def test_soft_skip_not_initialized(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    # No .fits directory → soft skip via compute_registry_delta
    with patch("bellman.graph.delta.libfits_available", return_value=True):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    assert result.ok_value.registry_error is not None
    assert "init" in result.ok_value.registry_error.lower()


def test_format_global_issues_and_registry_details(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "shared-name")
    layout.create_project(tmp_path, "shared-name")
    _write_goal(tmp_path, "broken", "# Nope\n\nBody.\n")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    # Inject multiple issues on one entity for multi-line formatting.
    status = result.ok_value
    entities = list(status.entities)
    for i, entity in enumerate(entities):
        if entity.name == "broken":
            entities[i] = type(entity)(
                kind=entity.kind,
                name=entity.name,
                path=entity.path,
                markdown="invalid",
                issues=("first issue", "second issue"),
                registry="n/a",
                node=entity.node,
            )
    from bellman.report.status import RoadmapStatus

    status = RoadmapStatus(
        root=status.root,
        entities=tuple(entities),
        global_issues=status.global_issues,
        registry=None,
        registry_error=status.registry_error,
    )
    buf = StringIO()
    format_status_report(status, buf)
    output = buf.getvalue()
    assert "Global issues" in output
    assert "global issue" in output
    assert "second issue" in output
    assert "Work packages" not in output or "shared-name" in output


def test_format_full_registry_section(tmp_path: Path) -> None:
    from bellman.report.status import EntityStatus, RoadmapStatus

    delta = RegistryDelta(
        missing_nodes=("goal a",),
        extra_nodes=("goal b",),
        missing_links=("parent_of x -> y",),
        extra_links=("depends_on p -> q",),
        needs_id_migration=True,
        missing_node_ids=frozenset({DesiredNode("goal", "goal/a")}),
        extra_node_ids=frozenset({DesiredNode("goal", "goal/b")}),
        desired_node_count=2,
        actual_node_count=2,
        desired_link_count=1,
        actual_link_count=1,
    )
    status = RoadmapStatus(
        root=str(tmp_path),
        entities=(
            EntityStatus(
                kind="goal",
                name="a",
                path=None,
                markdown="ok",
                issues=(),
                registry="missing",
                node=DesiredNode("goal", "goal/a"),
            ),
        ),
        global_issues=(),
        registry=delta,
        registry_error=None,
    )
    buf = StringIO()
    format_status_report(status, buf)
    output = buf.getvalue()
    assert "Extra nodes:" in output
    assert "Missing links:" in output
    assert "Extra links:" in output
    assert "Legacy ID migration: yes" in output
    assert "registry node delta" in output


def test_format_registry_matches(tmp_path: Path) -> None:
    from bellman.report.status import RoadmapStatus

    delta = RegistryDelta(
        missing_nodes=(),
        extra_nodes=(),
        missing_links=(),
        extra_links=(),
        desired_node_count=0,
        actual_node_count=0,
    )
    status = RoadmapStatus(
        root=str(tmp_path),
        entities=(),
        global_issues=(),
        registry=delta,
        registry_error=None,
    )
    buf = StringIO()
    format_status_report(status, buf)
    assert "Registry matches git." in buf.getvalue()


def test_archived_initiative_in_status(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "old-idea")
    src = layout.initiative_path(tmp_path, "old-idea")
    dest = layout.archived_initiative_path(tmp_path, "old-idea")
    src.rename(dest)
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    archived = next(
        e for e in result.ok_value.entities if e.kind == "archived_initiative"
    )
    assert archived.name == "old-idea"
    buf = StringIO()
    format_status_report(result.ok_value, buf)
    assert "Archived initiatives" in buf.getvalue()


def test_unparseable_initiative_and_milestone(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / "initiatives" / "bad-init.md").write_text("nope\n", encoding="utf-8")
    (tmp_path / "milestones" / "bad-ms.md").write_text("nope\n", encoding="utf-8")
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    names = {e.name: e for e in result.ok_value.entities}
    assert names["bad-init"].markdown == "unparsed"
    assert names["bad-ms"].markdown == "unparsed"


def test_unparseable_project_md(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    project_dir = tmp_path / "projects" / "broken-proj"
    project_dir.mkdir(parents=True)
    (project_dir / "broken-proj.md").write_text("nope\n", encoding="utf-8")
    (project_dir / "work-packages.yaml").write_text(
        "version: 1\n\nwork_packages: []\n", encoding="utf-8"
    )
    result = compute_roadmap_status(tmp_path, registry=False)
    assert isinstance(result, Ok)
    proj = next(e for e in result.ok_value.entities if e.name == "broken-proj")
    assert proj.markdown == "unparsed"


def test_synced_entities_with_registry(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "ok-goal", "# Ok Goal\n\nBody.\n")
    (tmp_path / ".fits").mkdir()
    node = DesiredNode("goal", "goal/ok-goal")
    delta = RegistryDelta(
        missing_nodes=(),
        extra_nodes=(),
        missing_links=(),
        extra_links=(),
        missing_node_ids=frozenset(),
        extra_node_ids=frozenset(),
        desired_node_count=1,
        actual_node_count=1,
    )
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Ok(delta),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    goal = next(e for e in result.ok_value.entities if e.name == "ok-goal")
    assert goal.registry == "synced"
    assert goal.node == node


def test_entity_marked_extra_when_in_extra_set(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    _write_goal(tmp_path, "ok-goal", "# Ok Goal\n\nBody.\n")
    node = DesiredNode("goal", "goal/ok-goal")
    delta = RegistryDelta(
        missing_nodes=(),
        extra_nodes=("goal ok-goal",),
        missing_links=(),
        extra_links=(),
        extra_node_ids=frozenset({node}),
        desired_node_count=0,
        actual_node_count=1,
    )
    with patch(
        "bellman.report.status.compute_registry_delta",
        return_value=Ok(delta),
    ):
        result = compute_roadmap_status(tmp_path, registry=True)
    assert isinstance(result, Ok)
    goal = next(e for e in result.ok_value.entities if e.name == "ok-goal")
    assert goal.registry == "extra"
    # Covered extra should not duplicate the inventory row.
    extras = [e for e in result.ok_value.entities if e.registry == "extra"]
    assert len(extras) == 1


def test_helper_kind_and_display_names() -> None:
    from bellman.report.status import _display_name_for_node, _kind_from_desired_node

    assert _kind_from_desired_node(DesiredNode("work_package", "p/a/b")) == (
        "work_package"
    )
    assert _kind_from_desired_node(DesiredNode("initiative", "initiative/x")) == (
        "initiative"
    )
    assert _kind_from_desired_node(DesiredNode("project", "project/x")) == "project"
    assert _kind_from_desired_node(DesiredNode("milestone", "milestone/x")) == (
        "milestone"
    )
    assert _kind_from_desired_node(DesiredNode("goal", "goal/x")) == "goal"
    assert (
        _display_name_for_node(DesiredNode("work_package", "project/foo/bar"))
        == "foo/bar"
    )
    assert _display_name_for_node(DesiredNode("goal", "goal/x")) == "x"


def test_node_for_kind_name_helpers() -> None:
    from bellman.report.status import _node_for_kind_name

    assert _node_for_kind_name("initiative", "a") is not None
    assert _node_for_kind_name("archived_initiative", "a") is not None
    assert _node_for_kind_name("project", "a") is not None
    assert _node_for_kind_name("work_package", "proj/slug") is not None
    assert _node_for_kind_name("work_package", "noslug") is None
    assert _node_for_kind_name("milestone", "m") is not None
    assert _node_for_kind_name("goal", "g") is not None


def test_infer_paths_and_wp_regex(tmp_path: Path) -> None:
    from bellman.report.status import _infer_entity_from_path, _key_for_issue_path

    layout.ensure_roadmap_dirs(tmp_path)
    assert _infer_entity_from_path(
        tmp_path, str(tmp_path / "initiatives" / "x.archived.md")
    ) == ("archived_initiative", "x")
    assert _infer_entity_from_path(
        tmp_path, str(tmp_path / "projects" / "p" / "work-packages.yaml")
    ) == ("project", "p")
    assert _infer_entity_from_path(tmp_path, str(tmp_path / "other" / "x.md")) is None
    assert _infer_entity_from_path(tmp_path, "/outside/file.md") is None

    wp_path = f"{tmp_path}/projects/billing/work-packages.yaml (wp-a)"
    assert _key_for_issue_path(tmp_path, wp_path, {}) == "work_package:billing/wp-a"
    assert _key_for_issue_path(tmp_path, str(tmp_path), {}) is None


def test_format_registry_unavailable_fallback(tmp_path: Path) -> None:
    from bellman.report.status import RoadmapStatus

    status = RoadmapStatus(
        root=str(tmp_path),
        entities=(),
        global_issues=(),
        registry=None,
        registry_error=None,
    )
    buf = StringIO()
    format_status_report(status, buf)
    assert "Registry check not available." in buf.getvalue()


class _FakeRepo:
    def __init__(self, *, graph: Graph) -> None:
        self._graph = graph

    def __enter__(self) -> _FakeRepo:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def output_graph(self, *, include_nested: bool = False) -> Ok[Graph]:
        return Ok(self._graph)
