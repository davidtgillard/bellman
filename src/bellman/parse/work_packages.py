"""Parse work-packages.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from bellman.model import (
    UNKNOWN_ESTIMATE,
    Estimate,
    Hardness,
    PrecedenceEdge,
    RelationType,
    ThreePointEstimate,
    WorkPackage,
)
from bellman.naming import slugify, validate_kebab

_DEPENDENCY_RE = re.compile(
    r"^\s*after:\s*(?P<predecessor>\S+)\s*"
    r"\[(?P<relation>FF|FS|SF|SS),\s*(?P<hardness>Mandatory|Discretionary|Optional)\]\s*$"
)
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([hdw])$", re.IGNORECASE)


def _slug_from_title(title: str) -> str:
    try:
        validate_kebab(title)
        return title
    except ValueError:
        return slugify(title)


def _invalid_estimate_msg(slug: str, path: str) -> str:
    return (
        f"estimate must be unknown or a complete 3-point estimate "
        f"for work package {slug!r} in {path}"
    )


def _invalid_duration_msg(slug: str, path: str, field: str) -> str:
    return (
        f"estimate {field} must be a duration with h, d, or w suffix "
        f"for work package {slug!r} in {path}"
    )


def _parse_duration_component(
    raw: Any,
    path: str,
    slug: str,
    field: str,
) -> tuple[float, str]:
    if isinstance(raw, str) and raw.strip().lower() == "unknown":
        msg = (
            f"partial estimate with unknown values is not supported "
            f"for work package {slug!r} in {path}"
        )
        raise ValueError(msg)
    if not isinstance(raw, str):
        raise ValueError(_invalid_duration_msg(slug, path, field))
    match = _DURATION_RE.match(raw.strip())
    if match is None:
        raise ValueError(_invalid_duration_msg(slug, path, field))
    return float(match.group(1)), match.group(2).lower()


def _parse_estimate_value(raw: Any, path: str, slug: str) -> Estimate:
    if isinstance(raw, str):
        if raw.strip().lower() == "unknown":
            return UNKNOWN_ESTIMATE
        raise ValueError(_invalid_estimate_msg(slug, path))
    if not isinstance(raw, dict):
        raise ValueError(_invalid_estimate_msg(slug, path))
    if "unit" in raw:
        msg = (
            f"estimate must not include unit; use h, d, or w suffixes "
            f"for work package {slug!r} in {path}"
        )
        raise ValueError(msg)
    required = ("optimistic", "most_likely", "pessimistic")
    if not all(k in raw for k in required):
        msg = f"incomplete estimate for work package {slug!r} in {path}"
        raise ValueError(msg)
    values: dict[str, float] = {}
    units: set[str] = set()
    for key in required:
        amount, unit = _parse_duration_component(raw[key], path, slug, key)
        values[key] = amount
        units.add(unit)
    if len(units) != 1:
        msg = (
            f"estimate values must use the same duration suffix "
            f"for work package {slug!r} in {path}"
        )
        raise ValueError(msg)
    unit = units.pop()
    optimistic = values["optimistic"]
    most_likely = values["most_likely"]
    pessimistic = values["pessimistic"]
    if not optimistic <= most_likely <= pessimistic:
        msg = (
            f"estimate must satisfy optimistic <= most_likely <= pessimistic "
            f"for work package {slug!r} in {path}"
        )
        raise ValueError(msg)
    return ThreePointEstimate(
        optimistic=optimistic,
        most_likely=most_likely,
        pessimistic=pessimistic,
        unit=unit,  # type: ignore[arg-type]
    )


def _parse_dependency_item(raw: Any, path: str, slug: str) -> PrecedenceEdge:
    if isinstance(raw, str):
        match = _DEPENDENCY_RE.match(raw.strip())
        if match is None:
            msg = (
                f"invalid dependency syntax for work package {slug!r} "
                f"in {path}: {raw!r}"
            )
            raise ValueError(msg)
        return PrecedenceEdge(
            predecessor=match.group("predecessor"),
            successor="",
            relation=RelationType(match.group("relation")),
            hardness=Hardness(match.group("hardness")),
        )
    if not isinstance(raw, dict):
        msg = f"invalid dependency for work package {slug!r} in {path}"
        raise ValueError(msg)
    after = raw.get("after")
    if not isinstance(after, str) or not after.strip():
        msg = f"dependency missing after for work package {slug!r} in {path}"
        raise ValueError(msg)
    relation_raw = raw.get("relation", "FS")
    hardness_raw = raw.get("hardness", "Mandatory")
    try:
        relation = RelationType(str(relation_raw))
        hardness = Hardness(str(hardness_raw))
    except ValueError as exc:
        msg = f"invalid dependency for work package {slug!r} in {path}: {exc}"
        raise ValueError(msg) from exc
    return PrecedenceEdge(
        predecessor=after.strip(),
        successor="",
        relation=relation,
        hardness=hardness,
    )


def _parse_dependencies(
    raw: Any,
    path: str,
    slug: str,
    *,
    project_name: str,
) -> tuple[PrecedenceEdge, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        msg = f"dependencies must be a list for work package {slug!r} in {path}"
        raise ValueError(msg)
    successor = f"{project_name}/{slug}"
    edges: list[PrecedenceEdge] = []
    for item in raw:
        edge = _parse_dependency_item(item, path, slug)
        edges.append(
            PrecedenceEdge(
                predecessor=edge.predecessor,
                successor=successor,
                relation=edge.relation,
                hardness=edge.hardness,
            )
        )
    return tuple(edges)


def _parse_wp_node(
    raw: Any,
    path: str,
    *,
    project_name: str,
) -> WorkPackage:
    if not isinstance(raw, dict):
        msg = f"work package entry must be a mapping in {path}"
        raise ValueError(msg)
    title_raw = raw.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        msg = f"work package missing title in {path}"
        raise ValueError(msg)
    title = title_raw.strip()
    slug = _slug_from_title(title)
    description_raw = raw.get("description")
    if not isinstance(description_raw, str):
        msg = f"work package {slug!r} missing description in {path}"
        raise ValueError(msg)
    notes_raw = raw.get("notes", "")
    if notes_raw is None:
        notes = ""
    elif isinstance(notes_raw, str):
        notes = notes_raw
    else:
        msg = f"work package {slug!r} notes must be a string in {path}"
        raise ValueError(msg)
    if "estimate" in raw:
        estimate = _parse_estimate_value(raw["estimate"], path, slug)
    else:
        estimate = None
    sub_raw = raw.get("sub_packages", [])
    if sub_raw is None:
        sub_raw = []
    if not isinstance(sub_raw, list):
        msg = f"sub_packages must be a list for work package {slug!r} in {path}"
        raise ValueError(msg)
    sub_packages = tuple(
        _parse_wp_node(item, path, project_name=project_name) for item in sub_raw
    )
    dependencies = _parse_dependencies(
        raw.get("dependencies"),
        path,
        slug,
        project_name=project_name,
    )
    return WorkPackage(
        slug=slug,
        title=title,
        description=description_raw,
        notes=notes,
        estimate=estimate,
        sub_packages=sub_packages,
        dependencies=dependencies,
    )


def parse_work_packages(path: Path, *, project_name: str) -> list[WorkPackage]:
    """Parse root work packages from work-packages.yaml."""
    rel = str(path)
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in {rel}: {exc}"
        raise ValueError(msg) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        msg = f"work-packages file must be a mapping in {rel}"
        raise ValueError(msg)
    version = data.get("version", 1)
    if version != 1:
        msg = f"unsupported work-packages version {version!r} in {rel}"
        raise ValueError(msg)
    raw_packages = data.get("work_packages", [])
    if raw_packages is None:
        raw_packages = []
    if not isinstance(raw_packages, list):
        msg = f"work_packages must be a list in {rel}"
        raise ValueError(msg)
    return [
        _parse_wp_node(item, rel, project_name=project_name) for item in raw_packages
    ]
