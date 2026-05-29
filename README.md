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
```

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
