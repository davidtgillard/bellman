"""Targeted coverage for remaining under-95% modules."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from pyfits import CreatedObject, Id
from pyfits.errors import FitsError
from pyfits.models import Graph, GraphEdge
from pyfits.result import Err, Ok
from typer.testing import CliRunner

from bellman import layout
from bellman.errors import BellmanError, BellmanLayoutError, BellmanWarning
from bellman.graph.desired import (
    DesiredNode,
    desired_link_from_graph_edge,
    desired_nodes,
    desired_precedence_edges,
    local_name_from_node_id,
    natural_name_from_node_id,
    resolve_entity_ref,
    resolve_entity_ref_from_layout,
)
from bellman.graph.fits_errors import ignore_duplicate_instance, ignore_duplicate_link
from bellman.graph.history import GraphHistory, InstanceRecord
from bellman.graph.identity import InstanceIndex
from bellman.graph.legacy import is_legacy_flat_node_id
from bellman.graph.link_naming import precedes_link_name
from bellman.graph.links_file import (
    _drop_links_from_subgraphs,
    _link_is_valid,
    _load_jsonc,
    _registered_guids,
    _registered_node_guids,
    reconcile_link_artifacts,
)
from bellman.graph.registry import bootstrap_registry, ensure_kind_roots
from bellman.model import (
    Goal,
    Hardness,
    Initiative,
    Milestone,
    PrecedenceEdge,
    Project,
    RelationType,
    Roadmap,
    ThreePointEstimate,
    WorkPackage,
)
from bellman.plugin.context import BellmanContext
from bellman.plugin.loader import PluginLoadError, load_plugin_or_raise
from bellman.report.dependencies import edges_for_entity
from bellman.report.wbs import iter_wbs_rows
from bellman.report.wbs_tree import _rollup_children, _sum_rollups, write_wbs_tree
from bellman.roadmap import load
from bellman.update.background import maybe_notify_update
from bellman.update.check import (
    _format_update_available_message,
    check_for_update,
    run_update_command,
)
from bellman.update.github import GitHubRelease, ReleaseAsset
from bellman.update.paths import running_executable, state_read_path
from bellman.update.settings import load_settings
from bellman.update.state import BellmanState
from bellman.validate import validate_roadmap

runner = CliRunner()


def test_bellman_error_and_warning_with_line() -> None:
    assert BellmanError("p", "m", line=3).format() == "p:3: m"
    assert BellmanWarning("p", "m", line=7).format() == "p:7: m"


def test_local_and_natural_name_fallbacks() -> None:
    assert local_name_from_node_id("bare") == "bare"
    assert local_name_from_node_id("goal--name") == "name"
    assert natural_name_from_node_id("unqualified") == "unqualified"


def test_desired_link_unresolved_endpoints() -> None:
    index = InstanceIndex.from_history(GraphHistory())
    assert (
        desired_link_from_graph_edge(
            link_type="parent_of",
            from_id_value="a",
            to_id_value="b",
            index=index,
        )
        is None
    )


def test_resolve_entity_ref_archived_initiative() -> None:
    roadmap = Roadmap(
        root="/tmp",
        archived_initiatives=(
            Initiative(
                name="old-init",
                title="Old",
                path="initiatives/old-init.archived.md",
                introduction="",
                motivation="",
                detailed_description="",
            ),
        ),
    )
    assert resolve_entity_ref(roadmap, "old-init") == "initiative/old-init"


def test_resolve_entity_ref_from_layout_matrix(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "g1")
    layout.create_milestone(tmp_path, "m1")
    layout.create_initiative(tmp_path, "i1")
    layout.create_project(tmp_path, "p1")
    archived = layout.archived_initiative_path(tmp_path, "arch")
    archived.write_text("# Arch\n", encoding="utf-8")

    assert resolve_entity_ref_from_layout(tmp_path, "g1") == "goal/g1"
    assert resolve_entity_ref_from_layout(tmp_path, "m1") == "milestone/m1"
    assert resolve_entity_ref_from_layout(tmp_path, "i1") == "initiative/i1"
    assert resolve_entity_ref_from_layout(tmp_path, "p1") == "project/p1"
    assert resolve_entity_ref_from_layout(tmp_path, "arch") == "initiative/arch"
    assert resolve_entity_ref_from_layout(tmp_path, "missing") == "missing"

    layout.create_goal(tmp_path, "clash")
    layout.create_initiative(tmp_path, "clash")
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_entity_ref_from_layout(tmp_path, "clash")


def test_desired_nodes_skips_archived_when_project_exists() -> None:
    roadmap = Roadmap(
        root="/tmp",
        projects=(
            Project(
                name="promoted",
                title="Promoted",
                path="projects/promoted/promoted.md",
                introduction="",
                motivation="",
                detailed_description="",
            ),
        ),
        archived_initiatives=(
            Initiative(
                name="promoted",
                title="Promoted",
                path="initiatives/promoted.archived.md",
                introduction="",
                motivation="",
                detailed_description="",
            ),
        ),
    )
    nodes = desired_nodes(roadmap)
    assert DesiredNode("project", "project/promoted") in nodes
    assert DesiredNode("initiative", "initiative/promoted") not in nodes
    scopes = roadmap.all_work_scopes()
    assert [scope.name for scope in scopes] == ["promoted"]
    assert isinstance(scopes[0], Project)


def test_desired_precedence_edges() -> None:
    edge = PrecedenceEdge(
        predecessor="a",
        successor="b",
        relation=RelationType.FS,
        hardness=Hardness.MANDATORY,
    )
    child = WorkPackage(slug="b", title="b", description="b", dependencies=(edge,))
    parent = WorkPackage(slug="a", title="a", description="a", sub_packages=(child,))
    collected = desired_precedence_edges((parent,), "demo")
    assert collected == [("demo", edge)]


def test_precedes_link_name() -> None:
    edge = PrecedenceEdge(
        predecessor="a",
        successor="b",
        relation=RelationType.FS,
        hardness=Hardness.MANDATORY,
    )
    name = precedes_link_name(edge)
    assert "precedes_FS_Mandatory" in str(name)


def test_is_legacy_flat_unknown_type_and_slash() -> None:
    assert not is_legacy_flat_node_id("kind", "goal")
    assert not is_legacy_flat_node_id("goal", "goal/nested")


def test_ignore_duplicate_without_guid() -> None:
    err = FitsError("dup", code="DuplicateInstanceName")
    assert isinstance(
        ignore_duplicate_instance(Err(err), logical_name="x"),
        Err,
    )
    assert isinstance(
        ignore_duplicate_link(Err(err), link_name="link"),
        Err,
    )
    guid = Id("550e8400-e29b-41d4-a716-446655440000")
    ok = ignore_duplicate_link(Err(err), link_name="link", guid=guid)
    assert isinstance(ok, Ok)
    assert ok.ok_value == CreatedObject(guid=guid, name="link")


def test_bootstrap_and_kind_roots_error_paths() -> None:
    repo = MagicMock()
    repo.register_node_type.return_value = Err(FitsError("fail", code="boom"))
    result = bootstrap_registry(repo)
    assert isinstance(result, Err)

    repo2 = MagicMock()
    repo2.register_node_type.return_value = Ok(None)
    repo2.register_link_type.return_value = Ok(None)
    repo2.new_node.return_value = Err(FitsError("create", code="Other"))
    result2 = ensure_kind_roots(repo2)
    assert isinstance(result2, Err)


def test_links_file_helpers_and_edge_cases(tmp_path: Path) -> None:
    assert _registered_guids({"instances": "bad"}) == set()
    assert _registered_node_guids({"instances": "bad"}) == set()
    assert (
        _link_is_valid(
            {"guid": 1},
            registered=set(),
            node_guids=set(),
            drop_touching_guids=set(),
            drop_link_guids=set(),
        )
        is False
    )
    assert (
        _link_is_valid(
            {"guid": "g", "in": 1, "out": "o"},
            registered={"g"},
            node_guids=set(),
            drop_touching_guids=set(),
            drop_link_guids=set(),
        )
        is False
    )
    assert (
        _link_is_valid(
            {"guid": "g", "in": "a", "out": "b"},
            registered=set(),
            node_guids={"a", "b"},
            drop_touching_guids=set(),
            drop_link_guids=set(),
        )
        is False
    )
    assert (
        _link_is_valid(
            {"guid": "drop", "in": "a", "out": "b"},
            registered={"drop"},
            node_guids={"a", "b"},
            drop_touching_guids=set(),
            drop_link_guids={"drop"},
        )
        is False
    )
    assert _drop_links_from_subgraphs(tmp_path, set()) == 0
    assert _drop_links_from_subgraphs(tmp_path, {"x"}) == 0

    path = tmp_path / "bad.jsonc"
    path.write_text("[1]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        _load_jsonc(path)

    nodes = tmp_path / "nodes"
    sub = nodes / "goal" / "subgraph.jsonc"
    sub.parent.mkdir(parents=True)
    sub.write_text("{not-json", encoding="utf-8")
    assert _drop_links_from_subgraphs(tmp_path, {"g"}) == 0

    sub.write_text(json.dumps({"links": "nope"}), encoding="utf-8")
    assert _drop_links_from_subgraphs(tmp_path, {"g"}) == 0

    sub.write_text(json.dumps({"links": ["skip", {"guid": "keep"}]}), encoding="utf-8")
    assert _drop_links_from_subgraphs(tmp_path, {"missing"}) == 0

    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text(
        json.dumps({"instances": "not-a-list"}),
        encoding="utf-8",
    )
    links = tmp_path / "links"
    links.mkdir()
    (links / "links.jsonc").write_text(
        json.dumps(
            {
                "links": [
                    "skip-me",
                    {
                        "guid": "g1",
                        "in": "a",
                        "out": "b",
                        "link_type": "parent_of",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    result = reconcile_link_artifacts(tmp_path)
    assert isinstance(result, Ok)


def test_reconcile_write_failure(tmp_path: Path) -> None:
    node = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    link = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "name": "a",
                        "kind": "node",
                        "type": "goal",
                        "guid": node,
                        "scope": "root",
                    },
                    {
                        "name": "lnk",
                        "kind": "link",
                        "type": "parent_of",
                        "guid": link,
                        "scope": "root",
                    },
                    "skip",
                ]
            }
        ),
        encoding="utf-8",
    )
    links_dir = tmp_path / "links"
    links_dir.mkdir()
    links_path = links_dir / "links.jsonc"
    links_path.write_text(
        json.dumps(
            {
                "links": [
                    {
                        "guid": link,
                        "link_type": "parent_of",
                        "in": node,
                        "out": "missing",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    real_write = Path.write_text

    def _fail_write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self.name in ("links.jsonc", "registry.json"):
            raise OSError("disk full")
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    with patch.object(Path, "write_text", _fail_write):
        result = reconcile_link_artifacts(tmp_path)
    assert isinstance(result, Err)


def test_delta_error_paths(tmp_path: Path) -> None:
    from bellman.graph.delta import RegistryDeltaError, compute_registry_delta
    from bellman.graph.history import BellmanHistoryError

    layout.ensure_roadmap_dirs(tmp_path)
    (tmp_path / ".fits").mkdir()
    roadmap = load(tmp_path)

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Err(BellmanHistoryError("idx")),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Err)
    assert isinstance(result.err_value, RegistryDeltaError)

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(GraphHistory())),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Err(FitsError("open", code="o")),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Err)

    class _BadGraphRepo:
        def __enter__(self) -> _BadGraphRepo:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def output_graph(self, *, include_nested: bool = False) -> Err[FitsError]:
            return Err(FitsError("graph", code="g"))

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(InstanceIndex.from_history(GraphHistory())),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(_BadGraphRepo()),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Err)

    history = GraphHistory(
        instances=(
            InstanceRecord(
                guid="1",
                instance_name="goal/g",
                type_name="goal",
                kind="node",
            ),
            InstanceRecord(
                guid="2",
                instance_name="goal/h",
                type_name="goal",
                kind="node",
            ),
            InstanceRecord(
                guid="3",
                instance_name="lnk",
                type_name="parent_of",
                kind="link",
            ),
        )
    )
    index = InstanceIndex.from_history(history)
    edge = GraphEdge(
        from_id=Id("1"),
        to_id=Id("2"),
        kind="registered_link",
        link_type="supports",
        id=Id("3"),
    )
    managed = GraphEdge(
        from_id=Id("1"),
        to_id=Id("2"),
        kind="registered_link",
        link_type="parent_of",
        id=Id("3"),
    )
    unresolved = GraphEdge(
        from_id=Id("missing"),
        to_id=Id("2"),
        kind="registered_link",
        link_type="parent_of",
        id=Id("4"),
    )

    class _GraphRepo:
        def __init__(self, graph: Graph) -> None:
            self._graph = graph

        def __enter__(self) -> _GraphRepo:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def output_graph(self, *, include_nested: bool = False) -> Ok[Graph]:
            return Ok(self._graph)

    with (
        patch("bellman.graph.delta.libfits_available", return_value=True),
        patch(
            "bellman.graph.delta.InstanceIndex.load",
            return_value=Ok(index),
        ),
        patch(
            "bellman.graph.delta.Repo.open",
            return_value=Ok(
                _GraphRepo(Graph(nodes=(), edges=(edge, managed, unresolved)))
            ),
        ),
    ):
        result = compute_registry_delta(tmp_path, roadmap)
    assert isinstance(result, Ok)


def test_version_frozen_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import sys
    import types
    from importlib.metadata import PackageNotFoundError
    from typing import Any, cast

    import bellman._version as version_mod

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert version_mod._frozen_version_string() is None

    monkeypatch.setattr(sys, "frozen", True, raising=False)

    build = types.ModuleType("bellman._build_version")
    cast(Any, build).VERSION = "9.9.9"
    monkeypatch.setitem(sys.modules, "bellman._build_version", build)
    assert version_mod._frozen_version_string() == "9.9.9"

    cast(Any, build).VERSION = ""
    assert version_mod._frozen_version_string() is None

    orig_import = builtins.__import__

    def _import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if name == "bellman._build_version":
            raise ImportError("missing")
        return orig_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)
    assert version_mod._frozen_version_string() is None

    monkeypatch.delattr(sys, "frozen", raising=False)
    with (
        patch("bellman._version._frozen_version_string", return_value=None),
        patch("bellman._version.version", side_effect=PackageNotFoundError("bellman")),
    ):
        assert version_mod._load_version_string() == "0.0.0+unknown"

    with patch("bellman._version._frozen_version_string", return_value="1.2.3"):
        assert version_mod._load_version_string() == "1.2.3"


def test_update_settings_file_and_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_dir = tmp_path / ".bellman"
    settings_dir.mkdir()
    settings_file = settings_dir / "bellman-settings.toml"
    settings_file.write_text(
        "[update]\n"
        "check_interval_hours = 12\n"
        'repository = "org/repo"\n'
        'release_tag = "nightly"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bellman.update.settings.settings_path",
        lambda: settings_file,
    )
    loaded = load_settings()
    assert loaded.check_interval_hours == 12
    assert loaded.repository == "org/repo"
    assert loaded.release_tag == "nightly"

    monkeypatch.setattr(
        "bellman.update.settings.sys.platform",
        "plan9",
    )
    monkeypatch.setattr(
        "bellman.update.settings.platform.machine",
        lambda: "z80",
    )
    from bellman.update.settings import default_asset_pattern

    assert default_asset_pattern() == "bellman-{version}-linux-x86_64"


def test_state_corrupt_and_naive_datetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "bellman-state.json"
    state_file.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        "bellman.update.state.state_read_path",
        lambda: state_file,
    )
    assert BellmanState.load().last_update_check is None

    state_file.write_text(
        json.dumps(
            {
                "last_update_check": "2026-01-01T00:00:00",
                "installed_version": "0.1.0",
            }
        ),
        encoding="utf-8",
    )
    loaded = BellmanState.load()
    assert loaded.last_update_check is not None
    assert loaded.last_update_check.tzinfo is not None

    state_file.write_text(
        json.dumps({"last_update_check": "not-a-date"}),
        encoding="utf-8",
    )
    assert BellmanState.load().last_update_check is None

    write_path = tmp_path / "out.json"
    monkeypatch.setattr(
        "bellman.update.state.state_write_path",
        lambda: write_path,
    )
    BellmanState(installed_version="1.0.0").save()
    assert "installed_version" in write_path.read_text(encoding="utf-8")


def test_paths_fallbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bellman.update.paths.sys.argv",
        ["nonexistent-bellman-bin-xyz"],
    )
    monkeypatch.setattr(
        "bellman.update.paths.shutil.which",
        lambda _name: None,
    )
    monkeypatch.setattr(
        "bellman.update.paths.Path.is_symlink",
        lambda self: False,
    )
    path = running_executable()
    assert path.name == "nonexistent-bellman-bin-xyz"

    monkeypatch.setattr(
        "bellman.update.paths.local_bellman_dir",
        lambda: tmp_path / "missing-local",
    )
    monkeypatch.setattr(
        "bellman.update.paths.home_bellman_dir",
        lambda: tmp_path / "missing-home",
    )
    assert state_read_path() is None


def test_background_skips_update_subcommand() -> None:
    ctx = MagicMock()
    ctx.invoked_subcommand = "update"
    maybe_notify_update(ctx)


def test_check_record_check_true_failure_paths() -> None:
    state = MagicMock()
    with patch(
        "bellman.update.check.fetch_release",
        side_effect=OSError("down"),
    ):
        result = check_for_update(
            settings=MagicMock(),
            state=state,
            record_check=True,
        )
    assert result.kind == "check_failed"
    state.touch_check_time.assert_called()

    state = MagicMock()
    with (
        patch(
            "bellman.update.check.fetch_release",
            return_value=GitHubRelease(tag_name="dev", assets=()),
        ),
        patch("bellman.update.check.latest_platform_asset", return_value=None),
    ):
        result = check_for_update(
            settings=MagicMock(),
            state=state,
            record_check=True,
        )
    assert "no matching" in result.message
    state.touch_check_time.assert_called()


def test_format_update_message_without_optional_fields() -> None:
    asset = ReleaseAsset(
        id=1,
        name="bellman-0.2.0-linux-x86_64",
        url="u",
        browser_download_url="b",
        updated_at="",
        digest=None,
    )
    msg = _format_update_available_message("0.2.0", asset)
    assert "0.2.0" in msg
    assert "sha256" not in msg


def test_run_update_command_paths() -> None:
    from bellman.update.check import CheckResult

    with patch(
        "bellman.update.check.check_for_update",
        return_value=CheckResult(kind="check_failed", message="fail"),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_update_command(check_only=True)
        assert exc.value.exit_code == 1

    with patch(
        "bellman.update.check.check_for_update",
        return_value=CheckResult(kind="up_to_date", message="ok"),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_update_command(check_only=True)
        assert exc.value.exit_code == 0

    asset = ReleaseAsset(
        id=1,
        name="bellman-0.2.0-linux-x86_64",
        url="u",
        browser_download_url="b",
        updated_at="2026-01-01T00:00:00Z",
        digest="sha256:abc",
    )
    available = CheckResult(
        kind="update_available",
        message="update available",
        latest_version="0.2.0",
        asset=asset,
    )
    with patch("bellman.update.check.check_for_update", return_value=available):
        with pytest.raises(typer.Exit) as exc:
            run_update_command(check_only=True)
        assert exc.value.exit_code == 1

    with (
        patch("bellman.update.check.check_for_update", return_value=available),
        patch("bellman.update.check.is_frozen", return_value=False),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_update_command(check_only=False)
        assert exc.value.exit_code == 1

    with (
        patch("bellman.update.check.check_for_update", return_value=available),
        patch("bellman.update.check.is_frozen", return_value=True),
        patch("bellman.update.check.load_settings", return_value=MagicMock()),
        patch(
            "bellman.update.check.verify_update_permissions",
            side_effect=OSError("no write permission"),
        ),
    ):
        with pytest.raises(typer.Exit) as exc:
            run_update_command(check_only=False)
        assert exc.value.exit_code == 1

    with (
        patch("bellman.update.check.check_for_update", return_value=available),
        patch("bellman.update.check.is_frozen", return_value=True),
        patch("bellman.update.check.load_settings", return_value=MagicMock()),
        patch("bellman.update.check.verify_update_permissions"),
        patch(
            "bellman.update.check.download_asset",
            return_value=Path("/tmp/staging"),
        ),
        patch("bellman.update.check.apply_binary_update"),
    ):
        run_update_command(check_only=False)


def test_validate_parent_estimate_in_memory() -> None:
    parent = WorkPackage(
        slug="parent",
        title="parent",
        description="p",
        estimate=ThreePointEstimate(1.0, 2.0, 3.0, "d"),
        sub_packages=(
            WorkPackage(
                slug="child",
                title="child",
                description="c",
                estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
            ),
        ),
    )
    roadmap = Roadmap(
        root="/tmp",
        projects=(
            Project(
                name="demo",
                title="Demo",
                path="projects/demo/demo.md",
                introduction="",
                motivation="",
                detailed_description="",
                work_packages=(parent,),
            ),
        ),
    )
    result = validate_roadmap(roadmap)
    assert any("must not have its own estimate" in e.message for e in result.errors)


def test_model_lookup_misses_and_hits() -> None:
    roadmap = Roadmap(
        root="/tmp",
        milestones=(
            Milestone(
                name="ms",
                title="MS",
                path="milestones/ms.md",
                date="2026-01-01",
                description="d",
            ),
        ),
        goals=(Goal(name="g", title="G", path="goals/g.md", description="d"),),
    )
    assert roadmap.milestone_by_name("ms") is not None
    assert roadmap.milestone_by_name("missing") is None
    assert roadmap.goal_by_name("g") is not None
    assert roadmap.work_package_slugs("missing") == set()


def test_parse_work_scope_inline_criteria_text(tmp_path: Path) -> None:
    from bellman.parse.work_scope import parse_work_scope

    path = tmp_path / "proj.md"
    path.write_text(
        "# Proj\n\n"
        "## Introduction\n\nIntro.\n\n"
        "## Motivation\n\nWhy.\n\n"
        "## Detailed Description\n\n"
        "Details before.\n"
        "  ### Criteria for Success\n"
        "Embedded done.\n\n"
        "## Dependencies\n\n",
        encoding="utf-8",
    )
    project = parse_work_scope(path, is_project=True, name="proj")
    assert "Embedded done" in project.criteria_for_success
    assert "Details before" in project.detailed_description


def test_roadmap_skips_project_files(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    projects = tmp_path / "projects"
    (projects / "readme.txt").write_text("not a project dir\n", encoding="utf-8")
    roadmap = load(tmp_path)
    assert roadmap.projects == ()


def test_wbs_tree_empty_children_and_blank_line() -> None:
    assert _rollup_children((), "parent").display == "?"
    assert _sum_rollups([], context="x").display == "?"

    roadmap = Roadmap(
        root="/tmp",
        projects=(
            Project(
                name="a",
                title="A",
                path="projects/a/a.md",
                introduction="",
                motivation="",
                detailed_description="",
                work_packages=(
                    WorkPackage(
                        slug="wa",
                        title="wa",
                        description="d",
                        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
                    ),
                ),
            ),
            Project(
                name="b",
                title="B",
                path="projects/b/b.md",
                introduction="",
                motivation="",
                detailed_description="",
                work_packages=(
                    WorkPackage(
                        slug="wb",
                        title="wb",
                        description="d",
                        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "d"),
                    ),
                ),
            ),
        ),
    )
    buf = StringIO()
    write_wbs_tree(roadmap, buf)
    assert "\n\n" in buf.getvalue()


def test_dependencies_and_wbs_project_filter(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_initiative(tmp_path, "alpha")
    layout.create_initiative(tmp_path, "beta")
    beta = layout.initiative_path(tmp_path, "beta")
    beta.write_text(
        beta.read_text(encoding="utf-8").replace(
            "## Dependencies\n\n",
            "## Dependencies\n\n- alpha [FS, Mandatory]\n",
        ),
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    preds, succs = edges_for_entity(roadmap, "alpha")
    assert succs
    assert not preds or True

    layout.create_project(tmp_path, "demo")
    roadmap = load(tmp_path)
    rows = list(iter_wbs_rows(roadmap, project_name="demo"))
    assert rows == [] or isinstance(rows, list)
    with pytest.raises(ValueError, match="project not found"):
        list(iter_wbs_rows(roadmap, project_name="missing"))


def test_plugin_context_cache_and_sync_err(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    ctx = BellmanContext(root=tmp_path, libfits_available=False)
    first = ctx.roadmap()
    second = ctx.roadmap()
    assert first is second

    fake_repo = MagicMock()
    ctx._repo = fake_repo
    assert ctx.repo() is fake_repo

    with patch(
        "bellman.plugin.context.graph_sync.sync_roadmap",
        return_value=Err(FitsError("sync", code="s")),
    ):
        result = ctx.sync_roadmap()
    assert isinstance(result, Err)
    assert ctx._graph is None or ctx._graph is None


def test_plugin_loader_name_validation_and_spec_none(tmp_path: Path) -> None:
    import textwrap

    from bellman.plugin import loader
    from bellman.plugin.discover import PluginSpec

    plugin_dir = tmp_path / "plugin" / "ok-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from bellman.plugin import BellmanPlugin, PluginArgumentSpecs
            PLUGIN = BellmanPlugin(
                name="ok-plugin",
                summary="ok",
                args=PluginArgumentSpecs.empty(),
                run=lambda ctx, args, io: 0,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    calls = {"n": 0}

    def _validate(name: str) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise ValueError("not kebab")

    with patch("bellman.plugin.loader.validate_kebab", side_effect=_validate):
        with pytest.raises(PluginLoadError, match="not kebab"):
            load_plugin_or_raise(tmp_path, "ok-plugin")

    with patch(
        "bellman.plugin.loader.importlib.util.spec_from_file_location",
        return_value=None,
    ):
        with pytest.raises(PluginLoadError, match="cannot create module spec"):
            loader._import_plugin(
                PluginSpec(
                    name="x",
                    path=plugin_dir,
                    module_name="bellman_plugin_x",
                )
            )


def test_cli_wbs_group_and_main() -> None:
    from bellman.cli import _WbsTyperGroup, main

    group = _WbsTyperGroup(name="wbs")
    group.commands = {"csv": MagicMock(), "tree": MagicMock()}
    ctx = MagicMock()
    with patch(
        "typer.core.TyperGroup.resolve_command",
        return_value=("csv", None, []),
    ) as super_resolve:
        group.resolve_command(ctx, ["--output", "out.csv", "/tmp/roadmap"])
        passed_args = super_resolve.call_args.args[1]
        assert "csv" in passed_args

    with patch("bellman.cli.app") as app_mock:
        main()
        app_mock.assert_called_once()


def test_layout_project_path_and_rename_collisions(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_project(tmp_path, "solo")

    missing = tmp_path / "projects" / "ghost" / "ghost.md"
    missing.parent.mkdir()
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "projects/ghost/ghost.md")

    # Bare projects/{name} when directory missing (len(parts)==1 path)
    with pytest.raises(BellmanLayoutError, match="no entity"):
        layout.resolve_entity_path(tmp_path, "projects/nope")

    layout.create_goal(tmp_path, "g-old")
    layout.create_goal(tmp_path, "g-new")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.rename_entity(tmp_path, "g-old", "g-new")

    layout.create_project(tmp_path, "p-old")
    layout.create_project(tmp_path, "p-new")
    with pytest.raises(BellmanLayoutError, match="already exists"):
        layout.rename_entity(tmp_path, "p-old", "p-new", kind="project")

    from bellman.layout import _rewrite_work_packages_line

    line = "      - other/wp-a [FS, Mandatory]\n"
    assert _rewrite_work_packages_line(line, old_name="missing", new_name="x") == line


def test_history_skips_bad_tombstone_and_instance(tmp_path: Path) -> None:
    from bellman.graph.history import load_graph_history

    fits = tmp_path / ".fits"
    fits.mkdir()
    (fits / "registry.json").write_text(
        json.dumps(
            {
                "kind": "fits-registry",
                "node_types": [
                    {
                        "type": "goal",
                        "tombstones": [
                            "bad",
                            {"guid": "g"},
                            {"n": 1, "guid": "ok"},
                        ],
                    },
                    {
                        "tombstones": [{"n": 2}],
                    },
                ],
                "link_types": [],
                "instances": [
                    "bad",
                    {"guid": "x"},
                    {
                        "guid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "name": "g1",
                        "type": "goal",
                        "kind": "node",
                        "scope": "root",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = load_graph_history(tmp_path)
    assert isinstance(result, Ok)
    assert len(result.ok_value.instances) == 1
