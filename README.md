# Bellman

Markdown-first roadmap planning built on [pyfits](https://github.com/davidtgillard/pyfits/).

## Install

Download the latest **linux-x86_64** binary from the rolling [`dev` release](https://github.com/davidtgillard/bellman/releases/tag/dev):

```bash
curl -fsSL -o bellman \
  "https://github.com/davidtgillard/bellman/releases/download/dev/bellman-0.1.0-linux-x86_64"
chmod +x bellman
sudo mv bellman /usr/local/bin/   # or any directory on your PATH
```

The asset name includes the version from `pyproject.toml` and changes when the version is bumped.

### Self-update

```bash
bellman update --check   # check only; exit 1 if a newer build is available
bellman update           # download and replace the binary (PyInstaller builds only)
```

Bellman checks for updates in the background (at most once per 24 hours by default) when you run any other subcommand.

After upgrading to a release that introduces type-qualified graph node IDs, run `bellman sync` once per roadmap so the pyfits registry is rebuilt under the new id scheme.

### Configuration

Settings live in `$HOME/.bellman/bellman-settings.toml`:

```toml
[update]
check_interval_hours = 24
timeout_seconds = 10
repository = "davidtgillard/bellman"
release_tag = "dev"
```

State (last check time, installed asset id) is stored in `.bellman/bellman-state.json` next to the `bellman` binary when possible, otherwise in `$HOME/.bellman/bellman-state.json`.

## About

Bellman defines a roadmap as initiatives, projects, work packages, milestones, and goals. Human-edited markdown is the source of truth; a pyfits graph is derived for validation and future tooling.

## Roadmap layout

```
initiatives/          # one .md per initiative (default)
projects/             # one folder per project
  {name}/
    {name}.md
    work-packages.yaml
milestones/
goals/
```

All natural names use **lowercase-kebab-case** (e.g. `billing-redesign`).

Run `bellman init` once at the roadmap root before other commands. It creates the markdown directories and the pyfits repository (`.fits/`, `nodes/`, `links/`). Graph sync commands do not create that scaffolding.

When you run a command from a subdirectory, bellman walks up to the nearest ancestor containing `.fits/`, stopping at the git root (the directory containing `.git`) so it does not search outside the work tree. `bellman init` always targets the path you give (or cwd) and does not walk upward.

## Commands

```bash
bellman init .
bellman create initiative explore-ml-ranking
bellman create project billing-redesign
bellman create milestone ga-release
bellman create goal reduce-churn
bellman promote billing-redesign   # after creating as initiative
bellman validate .
bellman validate --no-registry .
bellman sync .
bellman version
bellman update --check
bellman delete my-goal
bellman plugin list
bellman plugin my-plugin
bellman report wbs tree --project billing-redesign   # PERT tree to stdout
```

`validate` checks markdown in git and, by default, reports differences between those files and the pyfits registry (for example a goal added by hand without `bellman create`). Use `--no-registry` to skip registry comparison. `sync` runs the same markdown validation first, then updates the registry from git and prunes stale graph objects.

`create`, `delete`, and `promote` update the pyfits graph and `.fits/registry.json` directly when libfits is installed. Run `bellman init` first; `sync` will not bootstrap pyfits artifacts. If graph sync fails after a markdown change, the command exits with code 1; the markdown file is still written. When libfits is not available, those commands only change markdown and print a note. `delete` also prunes the removed entity from the graph; use `bellman sync` to reconcile other manual edits.

## Plugins

Repo-local Python plugins live under `plugin/{name}/` in the roadmap root. Each plugin exports a `PLUGIN` object (`BellmanPlugin` from `bellman.plugin`). Plugins require a **Python install** of bellman (`uv run bellman` or `pip install`); the standalone PyInstaller binary cannot load arbitrary repo Python.

```bash
bellman plugin --path /path/to/roadmap list
bellman plugin --path /path/to/roadmap my-plugin
bellman plugin --path /path/to/roadmap my-plugin --help    # per-plugin argparse help
```

When the shell cwd is inside the roadmap tree, omit `--path`; bellman discovers the root automatically.

Example `plugin/report-deps/__init__.py`:

```python
from bellman.plugin import (
    PluginArgumentSpecs,
    PluginArguments,
    BellmanContext,
    BellmanPlugin,
    TextIO,
)

def run(ctx: BellmanContext, args: PluginArguments, io: TextIO) -> int:
    for scope in ctx.roadmap().all_work_scopes():
        for edge in scope.dependencies:
            io.writeline(f"{edge.predecessor} -> {edge.successor}")
    return 0

PLUGIN = BellmanPlugin(
    name="report-deps",
    summary="Print scope precedence edges",
    args=PluginArgumentSpecs.empty(),
    run=run,
)
```

`BellmanContext` provides lazy access to the markdown roadmap (`roadmap()`), pyfits graph (`graph()`), registry audit history (`history()` — renames, tombstones, live instances from `.fits/registry.json`), and `sync_roadmap()`. Use `TextIO` for stdout/stderr so output is testable.

## Link naming

Links are identified as `{link_type}:{from}->{to}`. Precedence edges use registered types such as `precedes_FS_Mandatory`.

## libfits

Graph sync requires `libfits.so` (same as pyfits). The PyInstaller binary bundles libfits when built with `LIBFITS_PATH` set. For source installs, build the sibling [fits](https://github.com/davidtgillard/fits) checkout or set `PYFITS_LIB_PATH` to the shared library path.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
```

### Build a standalone binary

```bash
uv sync --all-groups
export LIBFITS_PATH=/path/to/libfits.so   # or build ../fits
uv run python packaging/write_build_version.py
uv run pyinstaller packaging/bellman.spec --noconfirm
./dist/bellman version
```

Integration tests are marked `@pytest.mark.integration` and skip when libfits is unavailable.
