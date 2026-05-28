"""Parse initiative and project markdown files."""

from __future__ import annotations

from pathlib import Path

from snark.model import Initiative, Project, WorkScope
from snark.naming import normalize_entity_name
from snark.parse._sections import section_by_title, split_sections
from snark.parse.dependencies import parse_dependencies_section
from snark.parse.work_packages import parse_work_packages


def _required_section(sections: list, title: str, path: str) -> str:
    sec = section_by_title(sections, title)
    if sec is None:
        msg = f"missing required section {title!r} in {path}"
        raise ValueError(msg)
    return sec.body


def parse_work_scope(
    path: Path,
    *,
    is_project: bool,
    work_packages_path: Path | None = None,
) -> Initiative | Project:
    """Parse a WorkScope markdown file."""
    text = path.read_text(encoding="utf-8")
    name = normalize_entity_name(path.stem)
    rel_path = str(path)
    title, sections = split_sections(text)
    if title is None:
        msg = f"missing title (# heading) in {rel_path}"
        raise ValueError(msg)

    introduction = _required_section(sections, "Introduction", rel_path)
    motivation = _required_section(sections, "Motivation", rel_path)
    detailed = _required_section(sections, "Detailed Description", rel_path)

    deps_sec = section_by_title(sections, "Dependencies")
    dep_body = deps_sec.body if deps_sec is not None else ""
    dependencies = tuple(parse_dependencies_section(dep_body, successor=name))

    base = WorkScope(
        name=name,
        title=title,
        path=rel_path,
        introduction=introduction,
        motivation=motivation,
        detailed_description=detailed,
        dependencies=dependencies,
    )

    if not is_project:
        return Initiative(
            name=base.name,
            title=base.title,
            path=base.path,
            introduction=base.introduction,
            motivation=base.motivation,
            detailed_description=base.detailed_description,
            dependencies=base.dependencies,
        )

    criteria = ""
    crit_l3 = next(
        (s for s in sections if s.level == 3 and s.title == "Criteria for Success"),
        None,
    )
    if crit_l3 is not None:
        criteria = crit_l3.body
    else:
        crit_sec = section_by_title(sections, "Criteria for Success")
        if crit_sec is not None:
            criteria = crit_sec.body
    if "### Criteria for Success" in detailed:
        parts = detailed.split("### Criteria for Success", maxsplit=1)
        detailed = parts[0].strip()
        if not criteria:
            criteria = parts[1].strip() if len(parts) > 1 else ""

    packages = ()
    if work_packages_path is not None and work_packages_path.is_file():
        packages = tuple(parse_work_packages(work_packages_path, project_name=name))

    return Project(
        name=base.name,
        title=base.title,
        path=base.path,
        introduction=base.introduction,
        motivation=base.motivation,
        detailed_description=detailed,
        dependencies=base.dependencies,
        criteria_for_success=criteria,
        work_packages=packages,
    )
