# Snark

Markdown-first roadmap planning built on [pyfits](https://github.com/davidtgillard/pyfits/).

## Install

Download the latest **linux-x86_64** binary from the rolling [`dev` release](https://github.com/davidtgillard/snark/releases/tag/dev):

```bash
curl -fsSL -o snark \
  "https://github.com/davidtgillard/snark/releases/download/dev/snark-0.1.0-linux-x86_64"
chmod +x snark
sudo mv snark /usr/local/bin/   # or any directory on your PATH
```

The asset name includes the version from `pyproject.toml` and changes when the version is bumped.

### Self-update

```bash
snark update --check   # check only; exit 1 if a newer build is available
snark update           # download and replace the binary (PyInstaller builds only)
```

Snark checks for updates in the background (at most once per 24 hours by default) when you run any other subcommand.

### Configuration

Settings live in `$HOME/.snark/snark-settings.toml`:

```toml
[update]
check_interval_hours = 24
timeout_seconds = 10
repository = "davidtgillard/snark"
release_tag = "dev"
```

State (last check time, installed asset id) is stored in `.snark/snark-state.json` next to the `snark` binary when possible, otherwise in `$HOME/.snark/snark-state.json`.

## About

Snark defines a roadmap as initiatives, projects, work packages, milestones, and goals. Human-edited markdown is the source of truth; a pyfits graph is derived for validation and future tooling.

## Roadmap layout

```
initiatives/          # one .md per initiative (default)
projects/             # one folder per project
  {name}/
    {name}.md
    work-packages.md
milestones/
goals/
```

All natural names use **lowercase-kebab-case** (e.g. `billing-redesign`).

Run `snark init` once at the roadmap root before other commands. It creates the markdown directories and the pyfits repository (`.fits/`, `nodes/`, `links/`). Graph sync commands do not create that scaffolding.

When you run a command from a subdirectory, snark walks up to the nearest ancestor containing `.fits/`, stopping at the git root (the directory containing `.git`) so it does not search outside the work tree. `snark init` always targets the path you give (or cwd) and does not walk upward.

## Commands

```bash
snark init .
snark create initiative explore-ml-ranking
snark create project billing-redesign
snark create milestone ga-release
snark create goal reduce-churn
snark promote billing-redesign   # after creating as initiative
snark validate .
snark version
snark update --check
snark delete my-goal
snark plugin list
snark plugin my-plugin
```

`create`, `delete`, and `promote` update the pyfits graph and `.fits/registry.json` when libfits is installed (same sync as `validate --sync`). Run `snark init` first; `validate --sync` will not bootstrap pyfits artifacts. If graph sync fails after the markdown change, the command exits with code 1; the markdown file is still written. When libfits is not available, those commands only change markdown and print a note. `delete` prunes removed entities from the graph; use `snark validate --prune` to prune stale objects after other edits.

## Plugins

Repo-local Python plugins live under `plugin/{name}/` in the roadmap root. Each plugin exports a `PLUGIN` object (`SnarkPlugin` from `snark.plugin`). Plugins require a **Python install** of snark (`uv run snark` or `pip install`); the standalone PyInstaller binary cannot load arbitrary repo Python.

```bash
snark plugin --path /path/to/roadmap list
snark plugin --path /path/to/roadmap my-plugin
snark plugin --path /path/to/roadmap my-plugin --help    # per-plugin argparse help
```

When the shell cwd is inside the roadmap tree, omit `--path`; snark discovers the root automatically.

Example `plugin/report-deps/__init__.py`:

```python
from snark.plugin import (
    PluginArgumentSpecs,
    PluginArguments,
    SnarkContext,
    SnarkPlugin,
    TextIO,
)

def run(ctx: SnarkContext, args: PluginArguments, io: TextIO) -> int:
    for scope in ctx.roadmap().all_work_scopes():
        for edge in scope.dependencies:
            io.writeline(f"{edge.predecessor} -> {edge.successor}")
    return 0

PLUGIN = SnarkPlugin(
    name="report-deps",
    summary="Print scope precedence edges",
    args=PluginArgumentSpecs.empty(),
    run=run,
)
```

`SnarkContext` provides lazy access to the markdown roadmap (`roadmap()`), pyfits graph (`graph()`), registry audit history (`history()` — renames, tombstones, live instances from `.fits/registry.json`), and `sync_roadmap()`. Use `TextIO` for stdout/stderr so output is testable.

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
uv run pyinstaller packaging/snark.spec --noconfirm
./dist/snark version
```

Integration tests are marked `@pytest.mark.integration` and skip when libfits is unavailable.
