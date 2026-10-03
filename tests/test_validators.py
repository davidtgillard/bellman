"""Custom Python validators under ``validator/``."""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from attr_support import (
    PRIORITY_JSONC,
    PROGRAM_JSONC,
    make_root,
    write_attribute,
    write_initiative,
    write_project,
)
from pyfits.result import Ok
from typer.testing import CliRunner

from bellman.cli import app
from bellman.errors import BellmanError, BellmanWarning
from bellman.report.status import compute_roadmap_status
from bellman.roadmap import load
from bellman.validators import (
    VALIDATOR_DIR,
    BellmanValidator,
    ValidationContext,
    ValidatorLoadError,
    discover_validators,
    load_validator,
    validate_roadmap_full,
)

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"

NO_P0 = """
from bellman.errors import BellmanError
from bellman.validators import BellmanValidator

def check(ctx):
    for ref in ctx.entities(kind="initiative"):
        if any(a.value == "P0" for a in ref.assignments("priority")):
            yield BellmanError(ref.path, "no P0 initiatives")

VALIDATOR = BellmanValidator(
    name="no-p0", summary="x", attributes=("priority",), run=check
)
"""


def _write_validator(
    root: Path, name: str, source: str, entry: str = "__init__.py"
) -> Path:
    directory = root / VALIDATOR_DIR / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / entry).write_text(textwrap.dedent(source), encoding="utf-8")
    return directory


def _setup(tmp_path: Path) -> Path:
    root = make_root(tmp_path)
    write_attribute(root, "priority", PRIORITY_JSONC)
    write_attribute(root, "program", PROGRAM_JSONC)
    return root


def _full(root: Path, **kwargs: bool):
    return validate_roadmap_full(root, load(root), **kwargs)


def _errors(root: Path, **kwargs: bool) -> list[str]:
    return [e.message for e in _full(root, **kwargs).errors]


def test_discover_ignores_missing_dir_files_and_empty_dirs(tmp_path: Path) -> None:
    assert discover_validators(tmp_path) == []
    base = tmp_path / VALIDATOR_DIR
    (base / "empty").mkdir(parents=True)
    (base / "notes.txt").write_text("x", encoding="utf-8")
    _write_validator(tmp_path, "b-init", "")
    _write_validator(tmp_path, "a-plugin", "", entry="plugin.py")
    specs = discover_validators(tmp_path)
    assert [s.name for s in specs] == ["a-plugin", "b-init"]
    assert specs[0].module_name == "bellman_validator_a_plugin"


def test_no_validators_returns_builtin_result(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_initiative(root, "alpha", ["priority: P1"])
    result = _full(root)
    assert result.errors == ()
    assert result.warnings == ()


def test_validator_reports_error_per_attribute_rule(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P0"])
    write_initiative(root, "beta", ["priority: P1"])
    messages = _errors(root)
    assert messages == ["no P0 initiatives"]


def test_validator_in_plugin_py_entry(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0, entry="plugin.py")
    write_initiative(root, "alpha", ["priority: P0"])
    assert _errors(root) == ["no P0 initiatives"]


def test_cross_attribute_validator_and_warnings(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(
        root,
        "p0-needs-program",
        """
        from bellman.errors import BellmanError, BellmanWarning
        from bellman.validators import BellmanValidator

        def check(ctx):
            assert ctx.definition("program") is not None
            assert ctx.definition("missing") is None
            assert len(ctx.catalog) == 2
            assert ctx.root.is_dir()
            for ref in ctx.entities(kind="project"):
                p0 = any(a.value == "P0" for a in ref.assignments("priority"))
                if p0 and not ref.assignments("program"):
                    yield BellmanError(ref.path, "P0 needs a program")
                elif not ref.assignments("program"):
                    yield BellmanWarning(ref.path, "consider a program")

        VALIDATOR = BellmanValidator(
            name="p0-needs-program",
            summary="s",
            attributes=["priority", "program"],
            run=check,
        )
        """,
    )
    write_project(root, "urgent", ["priority: P0"])
    write_project(root, "calm", ["priority: P1"])
    write_project(root, "ok", ["priority: P0", "program: platform-v2"])
    result = _full(root)
    assert [e.message for e in result.errors] == ["P0 needs a program"]
    assert [w.message for w in result.warnings] == ["consider a program"]


def test_validator_skipped_when_its_attribute_has_errors(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(
        root,
        "boom",
        """
        from bellman.validators import BellmanValidator

        def check(ctx):
            raise AssertionError("must not run")

        VALIDATOR = BellmanValidator(
            name="boom", summary="s", attributes=("priority",), run=check
        )
        """,
    )
    write_initiative(root, "alpha", ["priority: P9"])
    result = _full(root)
    assert len(result.errors) == 1
    assert "not allowed for attribute 'priority'" in result.errors[0].message
    (warning,) = result.warnings
    assert warning.message == (
        "validator 'boom' skipped: fix the errors for attribute(s) priority first"
    )


def test_validator_runs_when_only_other_attributes_have_errors(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P0", "program: nope"])
    messages = _errors(root)
    assert any("'program'" in m for m in messages)
    assert "no P0 initiatives" in messages


def test_validator_skipped_when_attribute_definition_is_invalid(
    tmp_path: Path,
) -> None:
    root = make_root(tmp_path)
    write_attribute(root, "priority", json.dumps({"name": "priority", "version": "x"}))
    _write_validator(root, "no-p0", NO_P0)
    messages = _errors(root)
    assert messages
    assert not any("unknown attribute" in m for m in messages)
    assert "no P0 initiatives" not in messages


def test_validator_with_unknown_attribute_is_an_error(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(
        root,
        "ghost",
        """
        from bellman.validators import BellmanValidator

        VALIDATOR = BellmanValidator(
            name="ghost", summary="s", attributes=("ghost-attr",), run=lambda ctx: []
        )
        """,
    )
    (message,) = _errors(root)
    assert "validator 'ghost' reads unknown attribute(s): ghost-attr" in message


def test_validator_exception_is_reported_not_raised(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(
        root,
        "crash",
        """
        from bellman.validators import BellmanValidator

        def check(ctx):
            raise RuntimeError("kaboom")

        VALIDATOR = BellmanValidator(
            name="crash", summary="s", attributes=("priority",), run=check
        )
        """,
    )
    (message,) = _errors(root)
    assert "validator 'crash' raised RuntimeError: kaboom" in message


def test_validator_returning_wrong_item_type(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(
        root,
        "sloppy",
        """
        from bellman.validators import BellmanValidator

        VALIDATOR = BellmanValidator(
            name="sloppy", summary="s", attributes=("priority",),
            run=lambda ctx: ["just a string"],
        )
        """,
    )
    (message,) = _errors(root)
    assert "returned str; expected BellmanError or BellmanWarning" in message


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("x = 1", "must define VALIDATOR as BellmanValidator"),
        ("raise ImportError('nope')", "import failed: nope"),
        ("def broken(:\n", "import failed"),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='other', summary='s',"
            " attributes=('priority',), run=lambda c: [])",
            "does not match directory",
        ),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='BadName', summary='s',"
            " attributes=('priority',), run=lambda c: [])",
            "must be lowercase kebab-case",
        ),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='bad-load', summary='s',"
            " attributes=(), run=lambda c: [])",
            "attributes must be a non-empty tuple",
        ),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='bad-load', summary='s',"
            " attributes=('Priority',), run=lambda c: [])",
            "attributes must be a non-empty tuple",
        ),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='bad-load', summary='s',"
            " attributes='priority', run=lambda c: [])",
            "attributes must be a non-empty tuple",
        ),
        (
            "from bellman.validators import BellmanValidator\n"
            "VALIDATOR = BellmanValidator(name='bad-load', summary='s',"
            " attributes=('priority',), run=None)",
            "run must be callable",
        ),
    ],
)
def test_load_validator_failures(tmp_path: Path, source: str, fragment: str) -> None:
    name = "BadName" if "BadName" in source else "bad-load"
    _write_validator(tmp_path, name, source)
    (spec,) = discover_validators(tmp_path)
    with pytest.raises(ValidatorLoadError, match=fragment) as excinfo:
        load_validator(spec)
    assert excinfo.value.path is not None


def test_load_failure_is_an_error_and_other_validators_still_run(
    tmp_path: Path,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "a-broken", "x = 1")
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P0"])
    messages = _errors(root)
    assert any(
        "validator 'a-broken': module must define VALIDATOR" in m for m in messages
    )
    assert "no P0 initiatives" in messages


def test_load_validator_returns_validator(tmp_path: Path) -> None:
    _write_validator(tmp_path, "no-p0", NO_P0)
    (spec,) = discover_validators(tmp_path)
    validator = load_validator(spec)
    assert isinstance(validator, BellmanValidator)
    assert validator.attributes == ("priority",)


def test_context_entities_filter_and_assignments(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    write_initiative(root, "alpha", ["priority: P1", "program: platform-v2"])
    write_project(root, "beta", ["priority: P0"])
    ctx = ValidationContext(roadmap=load(root), root=root)
    assert [e.name for e in ctx.entities("initiative")] == ["alpha"]
    assert {e.kind for e in ctx.entities()} == {"initiative", "project"}
    (alpha,) = ctx.entities("initiative")
    assert [a.value for a in alpha.assignments("program")] == ["platform-v2"]
    assert alpha.assignments("nope") == ()


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bellman.validators.runner.is_frozen", lambda: True)


def test_frozen_build_skips_validators_with_a_warning(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    _write_validator(root, "second", NO_P0.replace("no-p0", "second"))
    write_initiative(root, "alpha", ["priority: P0"])
    result = _full(root)
    assert result.errors == ()
    assert [w.message.split(":")[0] for w in result.warnings] == [
        "validator 'no-p0' skipped",
        "validator 'second' skipped",
    ]
    assert "standalone binary" in result.warnings[0].message


def test_frozen_build_require_validators_is_an_error(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P1"])
    result = _full(root, require_validators=True)
    assert result.warnings == ()
    assert [e.message.split(":")[0] for e in result.errors] == [
        "validator 'no-p0' skipped"
    ]


def test_cli_validate_warns_when_validators_are_skipped(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P1"])
    ok = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert ok.exit_code == 0, ok.output
    assert "skipped" in ok.output
    strict = runner.invoke(
        app, ["validate", str(root), "--no-registry", "--require-validators"]
    )
    assert strict.exit_code == 1
    assert "skipped" in strict.output


def test_cli_sync_require_validators(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P1"])
    strict = runner.invoke(app, ["sync", str(root), "--require-validators"])
    assert strict.exit_code == 1
    assert "skipped" in strict.output
    assert "Graph sync failed" not in strict.output
    with patch("bellman.cli.libfits_available", return_value=False):
        lax = runner.invoke(app, ["sync", str(root)])
    assert "skipped" in lax.output
    assert "Graph sync failed: libfits not available" in lax.output


def test_cli_validate_runs_validators(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P0"])
    result = runner.invoke(app, ["validate", str(root), "--no-registry"])
    assert result.exit_code == 1
    assert "no P0 initiatives" in result.output


def test_status_includes_validator_findings(tmp_path: Path) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P0"])
    result = compute_roadmap_status(root, registry=False)
    assert isinstance(result, Ok)
    status = result.ok_value
    issues = [i for e in status.entities for i in e.issues]
    assert any("no P0 initiatives" in i for i in issues)


def _status_issues(root: Path, *, require: bool) -> list[str]:
    result = compute_roadmap_status(root, registry=False, require_validators=require)
    assert isinstance(result, Ok)
    status = result.ok_value
    return list(status.global_issues) + [i for e in status.entities for i in e.issues]


def test_status_require_validators_turns_skip_into_error(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P1"])
    issues = _status_issues(root, require=True)
    assert any("validator 'no-p0' skipped" in i for i in issues)
    cli = runner.invoke(
        app, ["status", str(root), "--no-registry", "--require-validators"]
    )
    # status reports; it does not change its exit code
    assert cli.exit_code == 0, cli.output
    assert "validator 'no-p0' skipped" in cli.output


def test_status_without_flag_still_lists_the_skip(
    tmp_path: Path,
    frozen: None,
) -> None:
    root = _setup(tmp_path)
    _write_validator(root, "no-p0", NO_P0)
    write_initiative(root, "alpha", ["priority: P1"])
    assert any(
        "validator 'no-p0' skipped" in i for i in _status_issues(root, require=False)
    )


def test_example_roadmap_passes_with_its_validator() -> None:
    root = EXAMPLES
    result = validate_roadmap_full(root, load(root))
    assert result.errors == ()
    assert result.warnings == ()


def test_example_validator_flags_p0_project_without_program(tmp_path: Path) -> None:
    copy = tmp_path / "roadmap"
    shutil.copytree(EXAMPLES, copy, ignore=shutil.ignore_patterns("__pycache__"))
    md = copy / "projects" / "billing-redesign" / "billing-redesign.md"
    text = md.read_text(encoding="utf-8")
    text = text.replace("priority: P1", "priority: P0").replace(
        "- program@1.0: platform-v2 [allocation: 0.5]\n", ""
    )
    md.write_text(text, encoding="utf-8")
    messages = _errors(copy)
    assert messages == ["P0 projects must belong to a program"]


def test_error_and_warning_types_are_public() -> None:
    assert BellmanError("p", "m").format() == "p: m"
    assert BellmanWarning("p", "m", 3).format() == "p:3: m"
