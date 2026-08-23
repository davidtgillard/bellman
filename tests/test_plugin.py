"""CLI and loader tests for repo-local plugins."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bellman.cli import app
from bellman.plugin.loader import load_plugin_or_raise

runner = CliRunner()


def _write_echo_plugin(root: Path) -> None:
    plugin_dir = root / "plugin" / "echo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from bellman.plugin import (
                FlagSpec,
                PluginArgumentSpecs,
                BellmanContext,
                BellmanPlugin,
                PluginArguments,
                TextIO,
            )

            def _run(ctx: BellmanContext, args: PluginArguments, io: TextIO) -> int:
                io.writeline("echo")
                if args.verbose:
                    io.writeline(ctx.bellman_version)
                renames = ctx.history().renames
                io.writeline(f"renames:{len(renames)}")
                return 0

            PLUGIN = BellmanPlugin(
                name="echo",
                summary="Echo test plugin",
                args=PluginArgumentSpecs([FlagSpec("--verbose", help="Show version")]),
                run=_run,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_registry(root: Path) -> None:
    fits = root / ".fits"
    fits.mkdir(parents=True)
    (fits / "registry.json").write_text(
        json.dumps(
            {
                "description": "test",
                "version": 1,
                "kind": "fits-registry",
                "node_types": [],
                "link_types": [],
                "instance_renames": [],
            }
        ),
        encoding="utf-8",
    )


def test_plugin_list_and_run(tmp_path: Path) -> None:
    layout_dirs = ["initiatives", "projects", "milestones", "goals"]
    for name in layout_dirs:
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    _write_echo_plugin(tmp_path)

    result = runner.invoke(app, ["plugin", "--path", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "echo" in result.output
    assert "Echo test plugin" in result.output

    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "echo"],
    )
    assert result.exit_code == 0
    assert "echo" in result.output
    assert "renames:0" in result.output

    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "echo", "--verbose"],
    )
    assert result.exit_code == 0
    assert "echo" in result.output


def test_plugin_unknown_name(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    (tmp_path / "plugin").mkdir()
    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "missing"],
    )
    assert result.exit_code == 1
    assert "unknown plugin" in result.output


def test_load_plugin_name_mismatch(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin" / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from bellman.plugin import (
                PluginArgumentSpecs,
                BellmanPlugin,
                BellmanContext,
                PluginArguments,
                TextIO,
            )

            def _run(ctx, args, io):
                return 0

            PLUGIN = BellmanPlugin(
                name="other",
                summary="x",
                args=PluginArgumentSpecs.empty(),
                run=_run,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    from bellman.plugin.loader import PluginLoadError

    with pytest.raises(PluginLoadError, match="does not match"):
        load_plugin_or_raise(tmp_path, "bad")


def test_plugin_usage_without_args(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    result = runner.invoke(app, ["plugin", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "Usage:" in result.output


def test_plugin_list_empty_dir(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    (tmp_path / "plugin").mkdir()
    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    result = runner.invoke(app, ["plugin", "--path", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "No plugins found" in result.output


def test_plugin_list_missing_dir(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    result = runner.invoke(app, ["plugin", "--path", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "No plugin/ directory" in result.output


def test_plugin_list_load_error(tmp_path: Path) -> None:
    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    plugin_dir = tmp_path / "plugin" / "broken"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "raise RuntimeError('boom')\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["plugin", "--path", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "load error" in result.output


def test_plugin_help(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bellman.plugin.cli import _plugin_help

    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    _write_echo_plugin(tmp_path)
    _plugin_help(tmp_path, "echo")
    captured = capsys.readouterr()
    assert "Echo test plugin" in captured.out or "--verbose" in captured.out


def test_plugin_help_unknown(tmp_path: Path) -> None:
    import typer

    from bellman.plugin.cli import _plugin_help

    (tmp_path / "plugin").mkdir()
    with pytest.raises(typer.Exit) as exc_info:
        _plugin_help(tmp_path, "missing")
    assert exc_info.value.exit_code == 1


def test_plugin_dispatch_help_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from io import StringIO

    from bellman.plugin.cli import _dispatch_plugin
    from bellman.plugin.textio import TextIO

    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    _write_echo_plugin(tmp_path)
    code = _dispatch_plugin(
        tmp_path,
        "echo",
        ["-h"],
        TextIO(output_stream=StringIO(), error_stream=StringIO()),
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "--verbose" in captured.out or "Echo" in captured.out


def test_plugin_dispatch_bad_args(tmp_path: Path) -> None:
    from io import StringIO

    from bellman.plugin.cli import _dispatch_plugin
    from bellman.plugin.textio import TextIO

    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    _write_echo_plugin(tmp_path)
    code = _dispatch_plugin(
        tmp_path,
        "echo",
        ["--unknown-flag"],
        TextIO(output_stream=StringIO(), error_stream=StringIO()),
    )
    assert code != 0


def test_plugin_dispatch_no_plugin_dir(tmp_path: Path) -> None:
    (tmp_path / ".fits").mkdir()
    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    result = runner.invoke(
        app,
        ["plugin", "--path", str(tmp_path), "echo"],
    )
    assert result.exit_code == 1
    assert "No plugin/ directory" in result.output


def test_discover_skips_files_and_empty_dirs(tmp_path: Path) -> None:
    from bellman.plugin.discover import discover_plugins

    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "readme.txt").write_text("x", encoding="utf-8")
    (plugin_root / "empty").mkdir()
    good = plugin_root / "good"
    good.mkdir()
    (good / "plugin.py").write_text(
        textwrap.dedent(
            """
            from bellman.plugin import BellmanPlugin, PluginArgumentSpecs
            PLUGIN = BellmanPlugin(
                name="good",
                summary="g",
                args=PluginArgumentSpecs.empty(),
                run=lambda ctx, args, io: 0,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    specs = discover_plugins(tmp_path)
    assert [s.name for s in specs] == ["good"]


def test_discover_missing_plugin_root(tmp_path: Path) -> None:
    from bellman.plugin.discover import discover_plugins

    assert discover_plugins(tmp_path) == []


def test_load_plugin_or_raise_bad_kebab(tmp_path: Path) -> None:
    from bellman.plugin.loader import PluginLoadError, load_plugin_or_raise

    with pytest.raises(PluginLoadError, match="kebab-case"):
        load_plugin_or_raise(tmp_path, "Not_Valid")


def test_load_plugin_returns_none_on_error(tmp_path: Path) -> None:
    from bellman.plugin.loader import load_plugin

    assert load_plugin(tmp_path, "missing") is None


def test_load_plugin_missing_export(tmp_path: Path) -> None:
    from bellman.plugin.loader import PluginLoadError, load_plugin_or_raise

    plugin_dir = tmp_path / "plugin" / "empty"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(PluginLoadError, match="BellmanPlugin"):
        load_plugin_or_raise(tmp_path, "empty")


def test_load_plugin_import_failure(tmp_path: Path) -> None:
    from bellman.plugin.loader import PluginLoadError, load_plugin_or_raise

    plugin_dir = tmp_path / "plugin" / "boom"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "raise RuntimeError('nope')\n", encoding="utf-8"
    )
    with pytest.raises(PluginLoadError, match="import failed"):
        load_plugin_or_raise(tmp_path, "boom")


def test_load_plugin_via_plugin_py(tmp_path: Path) -> None:
    from bellman.plugin.loader import load_plugin_or_raise

    plugin_dir = tmp_path / "plugin" / "via-py"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        textwrap.dedent(
            """
            from bellman.plugin import BellmanPlugin, PluginArgumentSpecs
            PLUGIN = BellmanPlugin(
                name="via-py",
                summary="via plugin.py",
                args=PluginArgumentSpecs.empty(),
                run=lambda ctx, args, io: 0,
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    plugin = load_plugin_or_raise(tmp_path, "via-py")
    assert plugin.summary == "via plugin.py"


def test_plugin_load_error_format_with_path() -> None:
    from bellman.plugin.loader import PluginLoadError

    err = PluginLoadError("msg", path="/tmp/p")
    assert err.format() == "/tmp/p: msg"
    assert PluginLoadError("msg").format() == "msg"


def test_list_plugins_skips_failures(tmp_path: Path) -> None:
    from bellman.plugin.loader import list_plugins

    _write_echo_plugin(tmp_path)
    bad = tmp_path / "plugin" / "bad"
    bad.mkdir()
    (bad / "__init__.py").write_text("raise RuntimeError('x')\n", encoding="utf-8")
    plugins = list_plugins(tmp_path)
    assert [p.name for p in plugins] == ["echo"]


def test_args_duplicate_dest() -> None:
    from bellman.plugin.args import FlagSpec, PluginArgumentSpecs

    with pytest.raises(ValueError, match="duplicate argument dest"):
        PluginArgumentSpecs((FlagSpec("--verbose"), FlagSpec("--verbose")))


def test_args_invalid_option_name() -> None:
    from bellman.plugin.args import OptionSpec, _dest_for

    with pytest.raises(ValueError, match="invalid argument name"):
        _dest_for(OptionSpec("--bad name"))


def test_build_parser_option_and_positional() -> None:
    from bellman.plugin.args import (
        FlagSpec,
        OptionSpec,
        PluginArgumentSpecs,
        PositionalSpec,
        build_parser,
    )

    specs = PluginArgumentSpecs(
        (
            FlagSpec("verbose", help="v"),
            OptionSpec("--name", help="n", default="x"),
            PositionalSpec("target", help="t"),
        )
    )
    parser = build_parser("demo", "summary", specs)
    ns = parser.parse_args(["--verbose", "--name", "y", "z"])
    assert ns.verbose is True
    assert ns.name == "y"
    assert ns.target == "z"


def test_plugin_arguments_access() -> None:
    from argparse import Namespace

    from bellman.plugin.arguments import PluginArguments

    args = PluginArguments(Namespace(verbose=True))
    assert args.verbose is True
    assert args["verbose"] is True
    with pytest.raises(AttributeError):
        _ = args._secret
    with pytest.raises(AttributeError):
        _ = args.missing
    with pytest.raises(KeyError):
        _ = args["missing"]


def test_textio_methods(tmp_path: Path) -> None:
    from io import StringIO

    from bellman.plugin.textio import TextIO

    out = StringIO()
    err = StringIO()
    inp = StringIO("hello\nworld")
    io = TextIO(input_stream=inp, output_stream=out, error_stream=err)
    assert io.read(5) == "hello"
    assert io.readline() == "\n"
    assert io.write("a") == 1
    io.writeline("b")
    io.writeline("c\n")
    assert io.write_error("e") == 1
    io.writeline_error("f")
    assert "a" in out.getvalue()
    assert "b\n" in out.getvalue()
    assert "e" in err.getvalue()


def test_bellman_context_roadmap_and_history(tmp_path: Path) -> None:
    from unittest.mock import patch

    from pyfits.result import Err, Ok

    from bellman.graph.history import BellmanHistoryError, GraphHistory
    from bellman.plugin.context import BellmanContext

    for name in ("initiatives", "projects", "milestones", "goals"):
        (tmp_path / name).mkdir()
    _write_registry(tmp_path)
    ctx = BellmanContext(root=tmp_path, libfits_available=False)
    roadmap = ctx.roadmap()
    assert roadmap.root == tmp_path or str(roadmap.root).endswith(str(tmp_path.name))
    history = ctx.history()
    assert isinstance(history, GraphHistory)
    with pytest.raises(RuntimeError, match="libfits not available"):
        ctx.repo()
    with patch(
        "bellman.plugin.context.load_graph_history",
        return_value=Err(BellmanHistoryError("bad hist")),
    ):
        ctx2 = BellmanContext(root=tmp_path)
        with pytest.raises(RuntimeError, match="bad hist"):
            ctx2.history()
    with patch(
        "bellman.plugin.context.graph_sync.sync_roadmap",
        return_value=Ok(None),
    ) as sync_mock:
        result = ctx.sync_roadmap(prune=True)
        assert isinstance(result, Ok)
        sync_mock.assert_called_once()
    ctx.close()


def test_plugin_root_layout_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["plugin", "--path", str(empty), "list"])
    assert result.exit_code == 1
    assert (
        "roadmap" in result.output.lower()
        or "not found" in result.output.lower()
        or "no initialized" in result.output.lower()
    )


def test_long_option_variants() -> None:
    from bellman.plugin.args import _long_option

    assert _long_option("--foo") == "--foo"
    assert _long_option("-f") == "--f"
    assert _long_option("bar") == "--bar"


def test_bellman_context_repo_open_error(tmp_path: Path) -> None:
    from unittest.mock import patch

    from pyfits.errors import FitsError
    from pyfits.result import Err

    from bellman.plugin.context import BellmanContext

    ctx = BellmanContext(root=tmp_path, libfits_available=True)
    with patch(
        "bellman.plugin.context.Repo.open",
        return_value=Err(FitsError("open fail", code="t")),
    ):
        with pytest.raises(RuntimeError, match="open fail"):
            ctx.repo()


def test_bellman_context_graph_error(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from pyfits.errors import FitsError
    from pyfits.result import Err, Ok

    from bellman.plugin.context import BellmanContext

    fake_repo = MagicMock()
    fake_repo.output_graph.return_value = Err(FitsError("graph fail", code="t"))
    ctx = BellmanContext(root=tmp_path, libfits_available=True)
    with patch(
        "bellman.plugin.context.Repo.open",
        return_value=Ok(fake_repo),
    ):
        with pytest.raises(RuntimeError, match="graph fail"):
            ctx.graph()
    ctx._repo_owned = True
    ctx._repo = fake_repo
    ctx.close()
    fake_repo.close.assert_called_once()


def test_load_plugin_no_entry_file(tmp_path: Path) -> None:
    from bellman.plugin.discover import PluginSpec
    from bellman.plugin.loader import PluginLoadError, _import_plugin

    empty = tmp_path / "plugin" / "empty"
    empty.mkdir(parents=True)
    with pytest.raises(PluginLoadError, match="no __init__.py"):
        _import_plugin(
            PluginSpec(name="empty", path=empty, module_name="bellman_plugin_empty")
        )
