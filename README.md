# Snark

Markdown-first roadmap planning built on [pyfits](https://github.com/davidtgillard/pyfits/).

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
uv sync
snark init .
snark create initiative explore-ml-ranking
snark create project billing-redesign
snark create milestone ga-release
snark create goal reduce-churn
snark promote billing-redesign   # after creating as initiative
snark validate .
snark delete my-goal
```

## Link naming

Links are identified as `{link_type}:{from}->{to}`. Precedence edges use registered types such as `precedes_FS_Mandatory`.

## libfits

Graph sync requires `libfits.so` (same as pyfits). Build the sibling [fits](https://github.com/davidtgillard/fits) checkout or set `PYFITS_LIB_PATH` to the shared library path.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
```

Integration tests are marked `@pytest.mark.integration` and skip when libfits is unavailable.
