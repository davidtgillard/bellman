# Bellman

Markdown-first roadmap planning built on [pyfits](https://github.com/davidtgillard/pyfits/).

## Install

Download a platform binary from the rolling [`dev` release](https://github.com/davidtgillard/bellman/releases/tag/dev). Asset names include the version from `pyproject.toml`:

| Platform | Asset |
|----------|--------|
| Linux x86_64 | `bellman-{version}-linux-x86_64` |
| Windows x86_64 | `bellman-{version}-windows-x86_64.exe` |
| macOS arm64 | `bellman-{version}-macos-arm64` |

**Linux x86_64:**

```bash
curl -fsSL -o bellman \
  "https://github.com/davidtgillard/bellman/releases/download/dev/bellman-0.1.0-linux-x86_64"
chmod +x bellman
sudo mv bellman /usr/local/bin/   # or any directory on your PATH
```

**macOS arm64:**

```bash
curl -fsSL -o bellman \
  "https://github.com/davidtgillard/bellman/releases/download/dev/bellman-0.1.0-macos-arm64"
chmod +x bellman
sudo mv bellman /usr/local/bin/
```

**Windows x86_64** (PowerShell):

```powershell
Invoke-WebRequest -Uri "https://github.com/davidtgillard/bellman/releases/download/dev/bellman-0.1.0-windows-x86_64.exe" -OutFile bellman.exe
# Move bellman.exe onto your PATH
```

### Self-update

```bash
bellman update --check   # check only; exit 1 if a newer build is available
bellman update           # download and replace the binary (PyInstaller builds only)
```

`bellman update` selects the asset for the host platform automatically. Bellman also checks for updates in the background (at most once per 24 hours by default) when you run any other subcommand.

After upgrading to a release that uses libfits GUID wire ids (protocol v2), re-initialize each roadmap's pyfits tree: remove `.fits/`, `nodes/`, and `links/`, then run `bellman init .` and `bellman sync .`. Markdown remains the source of truth.

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
attributes/           # one {name}.jsonc per attribute definition (optional)
validator/            # optional Python validators (see Attributes)
```

All natural names use **lowercase-kebab-case** (e.g. `billing-redesign`).

Run `bellman init` once at the roadmap root before other commands. It creates the markdown directories and the pyfits repository (`.fits/`, `nodes/`, `links/`). Graph sync commands do not create that scaffolding.

`init`, `validate`, `status`, and `sync` take an optional path argument (default: the current working directory). When you run a command from a subdirectory, bellman walks up to the nearest ancestor containing `.fits/`, stopping at the git root (the directory containing `.git`) so it does not search outside the work tree. `bellman init` always targets the path you give (or cwd) and does not walk upward.

## Commands

```bash
bellman init
bellman create initiative explore-ml-ranking
bellman create project billing-redesign
bellman create milestone ga-release
bellman create goal reduce-churn
bellman promote billing-redesign   # after creating as initiative
bellman promote initiatives/billing-redesign
bellman demote billing-redesign    # park the project folder; restore the initiative
bellman demote projects/billing-redesign/billing-redesign.md
bellman validate
bellman validate --no-registry
bellman validate --require-validators   # fail instead of skipping Python validators
bellman sync --require-validators
bellman status --require-validators
bellman attribute rename program platform-v2 platform-v3
bellman status
bellman status --no-registry
bellman sync
bellman version
bellman update --check
bellman delete my-goal
bellman delete goals/my-goal.md
bellman rename old-name new-name
bellman rename projects/old-proj new-proj
bellman rename goal system-mci renamed-goal   # when names collide across types
bellman plugin list
bellman plugin my-plugin
bellman report wbs tree --project billing-redesign   # PERT tree to stdout
bellman report wbs tree --project projects/billing-redesign
bellman report dependencies                          # all precedence edges
bellman report deps beta                             # predecessors/successors of beta
bellman report deps initiatives/beta
bellman estimate billing-redesign                    # Monte Carlo effort and duration
bellman estimate billing-redesign --json --seed 1 --num-people 2
```

`validate` checks markdown in git and, by default, reports differences between those files and the pyfits registry (for example a goal added by hand without `bellman create`). Use `--no-registry` to skip registry comparison. `status` inventories every entity with markdown health and registry alignment without modifying files (exit 0 unless the command itself fails). `sync` runs the same markdown validation first, then updates the registry from git and prunes stale graph objects.

`create`, `delete`, `rename`, `promote`, and `demote` update the pyfits graph and `.fits/registry.json` directly when libfits is installed. Run `bellman init` first; `sync` will not bootstrap pyfits artifacts. If graph sync fails after a markdown change, the command exits with code 1; the markdown file is still written. When libfits is not available, those commands only change markdown and print a note. `delete` also prunes the removed entity from the graph; use `bellman sync` to reconcile other manual edits.

`demote` parks the whole project directory as `projects/{name}.archived/` (work packages and extra files included) and restores `initiatives/{name}.md`. A later `promote` of the same name restores that folder instead of creating an empty one. Promote and demote keep the same pyfits GUID and flip `instances[].type`; git history of `.fits/registry.json` is the type change.

`rename` moves the entity on disk (initiative, project, milestone, or goal), rewrites dependency references that name the old entity, and renames the matching pyfits instance (GUID preserved). Entity-targeting commands (`promote`, `demote`, `delete`, `rename`, `report deps`, `report wbs --project`) accept a bare name when it is unambiguous across types, a layout FQN such as `projects/foo` or `initiatives/foo`, a folder path (`projects/foo`), or the main markdown path (`projects/foo/foo.md`, `goals/foo.md`). Graph FQNs (`project/foo`, `goal/foo`) work as well. Use a type subcommand when initiative and goal (for example) share a name: `bellman rename goal foo bar`.

## Precedence dependencies

Declare predecessors **only on the successor** (the entity that depends on them). There is no `after:` / `before:` keyword.

**Initiatives and projects** — under `## Dependencies`:

```markdown
## Dependencies

- other-initiative [FS, Mandatory]
```

**Work packages** — in `work-packages.yaml` on the dependent package:

```yaml
dependencies:
  - predecessor: wp-setup
    relation: FS
    hardness: Mandatory
  # or: - wp-setup [FS, Mandatory]
```

Relation is one of `FF`, `FS`, `SF`, `SS`. Hardness is `Mandatory`, `Discretionary`, or `Optional`.

Use `bellman report dependencies` (alias `deps`) to list all edges, or pass an entity name / `project/slug` to see what it depends on and what depends on it.

## Project estimates

`bellman estimate <project>` samples each leaf work package from a Beta-PERT distribution and reports two summaries:

- **Effort** is work content: the sum of sampled leaf durations. That total does not grow with `--num-people`. Amdahl does not add coordination tasks to the WBS; it says only a fraction `p` of this work can run in parallel.
- **Duration** is calendar time: the larger of a staffed CPM list-schedule (FS forbids overlap; FF/SS/SF are start/finish constraints; unlinked leaves share `--num-people`) and Amdahl's law `effort * ((1 - p) + p / N)` with `--parallel-fraction` `p` (default 0.70) and `--num-people` `N` (default 1).

The parallelization *cost* shows up on the clock, not in effort. The serial remainder `(1 - p)` still takes `(1 - p) * effort` of calendar time no matter how many people you add, so extra staff sit through that remainder (or spend it on coordination). Staffed cost is therefore about `N * duration`, which is larger than effort when `N > 1` and `p < 1`. Example: `p = 0.70`, `N = 2` gives duration `0.65 * effort` and staffed cost `1.3 * effort`.

With the defaults (`N = 1`), duration equals effort. Use `--json` for a machine-readable document (schema version 1.0.0). `--seed` makes trials reproducible.

## Attributes

Attributes classify initiatives, projects, work packages, milestones, and goals with a name, a value, and optional data, without adding new entity types. Examples: a `priority` with fixed values, or a `program` that tags the work behind a large speculative scope and carries its own data. Attributes live only in bellman; they are not written to the pyfits graph.

### Defining an attribute

Each attribute is one JSONC file (JSON with `//` and `/* */` comments and trailing commas) at `attributes/{name}.jsonc`. **`{name}` is the attribute name** and must equal the file's `name` field (lowercase kebab-case). `bellman init` creates an empty `attributes/` directory; a roadmap without it still loads.

```jsonc
{
  "$schema": "https://github.com/davidtgillard/bellman/schemas/attribute-definition/1.0.json", // optional, for editors
  "name": "program",                    // must match the file name
  "version": "1.2",                     // x.y contract version, maintained by you (see Versions)
  "description": "Speculative work scope", // optional
  "applies_to": ["initiative", "project", "work_package"], // initiative, project, work_package, milestone, goal
  "cardinality": "many",                // "one": at most one assignment per entity; "many": any number
  "required": false,                    // true: every entity of an applicable kind needs this attribute
  "values": {                           // keyed values, each with its own data (see shapes below)
    "platform-v2": { "title": "Platform v2", "probability": 0.4 },
    "data-residency": { "title": "EU data residency" }
  },
  "value_schema": {                     // JSON Schema (2020-12) that each keyed entry must satisfy
    "type": "object",
    "required": ["title"],
    "properties": { "title": { "type": "string" }, "probability": { "type": "number" } }
  },
  "assignment_schema": {                // JSON Schema for data attached to one assignment
    "type": "object",
    "additionalProperties": false,
    "properties": { "allocation": { "type": "number", "minimum": 0, "maximum": 1 } }
  }
}
```

The shape of `values` picks one of three kinds of attribute:

| `values` | Meaning | `value_schema` |
| --- | --- | --- |
| a list of tokens, e.g. `["P0", "P1"]` | plain set: assignments must use one of the tokens | not allowed |
| an object keyed by token | keyed values: assignments use a key; each key carries data | optional, checks every entry |
| omitted | open: any value that matches the schema | required |

Tokens and keys start with a letter or digit and contain only letters, digits, `.`, `_` and `-`. For open attributes a value written in markdown (`budget: 12`) is read as a number or boolean when it looks like one before it is checked against `value_schema`. In markdown a value is a single token, so open attributes with object values can only be assigned on work packages (in `work-packages.yaml`); initiatives, projects, milestones and goals can use scalar open values. `assignment_schema` describes the optional per-assignment data (`[allocation: 0.5]`); data on an attribute without `assignment_schema` is rejected. bellman ships the JSON Schema for definition files (`attribute-definition-1.0.json`) and checks every file against it, then applies further checks (name matches file, embedded schemas are valid, keyed entries satisfy `value_schema`).

### Assigning attributes

Initiatives, projects, milestones, and goals use an optional `## Classifications` section:

```markdown
## Classifications

- priority: P1
- program@1.2: platform-v2 [allocation: 0.5]
```

The form is `- <name>[@x.y]: <value> [key: value, ...]`. Work packages use a `classifications` mapping in `work-packages.yaml`:

```yaml
work_packages:
  - title: Migrate ledger
    classifications:
      program@1.2:
        - value: platform-v2
          allocation: 0.5
      priority: P1        # a scalar or a list of scalars also works
```

Classifications are not inherited: a work package is not implicitly in its project's program.

### What validation checks

`bellman validate`, `sync`, and `status` report: unknown attributes, attributes used on a kind not in `applies_to`, values outside the allowed set or failing `value_schema`, data failing `assignment_schema`, duplicate assignments, more than one assignment for `cardinality: "one"`, version pin problems, and missing required attributes. A `required` attribute needs one assignment (at least one for `many`) on every entity whose kind is in `applies_to`, including every work package when `work_package` is listed. Entities that name an attribute whose definition is invalid are not also reported as unknown.

### Versions and pins

`version` is `x.y` and is yours to maintain: increase `y` for a backwards-compatible change (a new allowed value), and `x` for a breaking one (removing or renaming a value, changing a schema incompatibly). Nothing bumps it for you. An assignment can pin the version it was written against with `name@x.y`:

- same major, pin minor at or below the definition's: accepted
- pin major below the definition's: error, "pinned to an older major version... Review and update the pin."
- pin newer than the definition: error

An unpinned assignment is never flagged. After a breaking change, bump `x` and the old pins are listed for review.

### Custom validators

For rules a schema cannot express (such as "a P0 project must belong to a program"), put a Python validator in `validator/{name}/__init__.py` (or `plugin.py`). It exports `VALIDATOR`:

```python
from collections.abc import Iterable

from bellman.errors import BellmanError, BellmanWarning
from bellman.validators import BellmanValidator, ValidationContext


def run(ctx: ValidationContext) -> Iterable[BellmanError | BellmanWarning]:
    for project in ctx.entities(kind="project"):
        is_p0 = any(a.value == "P0" for a in project.assignments("priority"))
        if is_p0 and not project.assignments("program"):
            yield BellmanError(project.path, "P0 projects must belong to a program")


VALIDATOR = BellmanValidator(
    name="p0-needs-program",  # must match the directory name
    summary="P0 projects need a program",
    attributes=("priority", "program"),  # attributes it reads
    run=run,
)
```

Validators run after the built-in checks, and a validator is skipped when the built-in checks found errors for any attribute it lists (so it only sees well-formed data). An exception in a validator is reported as a validation error. Like plugins, validators need a **Python install** of bellman; the standalone binary skips them with a warning, and `--require-validators` on `bellman validate`, `bellman sync` and `bellman status` turns that warning into an error (use it in CI that runs the binary). `status` still exits 0; it only reports the skip as an error in its output. A validator held back because the built-in checks found errors for an attribute it lists is reported as a warning naming those attributes.

### Renaming a value

`bellman attribute rename <attribute> <old> <new>` changes a plain-set member or keyed value in the definition and in every assignment (markdown, `work-packages.yaml`, and parked project folders), keeping comments and layout. It refuses to run if any file cannot be rewritten safely, and writes nothing in that case. It does not change versions or pins; since a rename is a breaking change, bump the definition's major version afterwards.

See `examples/roadmap` for a working definition set and validator.

## Plugins

Repo-local Python plugins live under `plugin/{name}/` in the roadmap root. Each plugin exports a `PLUGIN` object (`BellmanPlugin` from `bellman.plugin`). Plugins require a **Python install** of bellman (`uv run bellman` or `pip install`); the standalone PyInstaller binary cannot load arbitrary repo Python.

```bash
bellman plugin --path /path/to/roadmap list
bellman plugin --path /path/to/roadmap my-plugin
bellman plugin --path /path/to/roadmap my-plugin --help    # per-plugin argparse help
```

When the shell cwd is inside the roadmap tree, omit `--path`; bellman discovers the root automatically.

Example `plugin/report-deps/__init__.py` (prefer built-in `bellman report dependencies` for this use case):

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

Graph sync requires the host-platform libfits shared library (`libfits.so`, `libfits.dll`, or `libfits.dylib`; same as pyfits). The PyInstaller binary bundles libfits when built with `LIBFITS_PATH` set. For source installs, run `python ../pyfits.git/scripts/fetch_libfits.py`, build the sibling [fits](https://github.com/davidtgillard/fits) checkout, or set `PYFITS_LIB_PATH`.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
```

### Build a standalone binary

```bash
uv sync --all-groups
python ../pyfits.git/scripts/fetch_libfits.py   # or export LIBFITS_PATH=...
uv run python packaging/write_build_version.py
uv run pyinstaller packaging/bellman.spec --noconfirm
uv run python packaging/package_release.py --platform linux-x86_64  # or windows-x86_64 / macos-arm64
./dist/bellman version
```

Integration tests are marked `@pytest.mark.integration` and skip when libfits is unavailable.
