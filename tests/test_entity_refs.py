"""Tests for type-qualified entity node ids and reference resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from bellman import layout
from bellman.graph.desired import (
    DesiredNode,
    entity_node_id,
    goal_node_id,
    milestone_node_id,
    natural_name_from_node_id,
    resolve_entity_ref,
    scope_node_id,
    wp_node_id,
)
from bellman.graph.legacy import is_legacy_flat_node_id, registry_needs_id_migration
from bellman.model import Goal, Initiative, Project, Roadmap
from bellman.roadmap import load
from bellman.validate import validate_roadmap

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_entity_node_id_qualifies_type() -> None:
    assert entity_node_id("goal", "reduce-churn") == "goal/reduce-churn"


def test_natural_name_from_node_id() -> None:
    assert natural_name_from_node_id("goal/reduce-churn") == "reduce-churn"
    assert natural_name_from_node_id("goal--reduce-churn") == "reduce-churn"
    assert natural_name_from_node_id("project/billing-redesign/wp-a") == "wp-a"


def test_goal_and_milestone_node_ids() -> None:
    assert goal_node_id("reduce-churn") == "goal/reduce-churn"
    assert milestone_node_id("ga-release") == "milestone/ga-release"
    assert wp_node_id("billing-redesign", "wp-a") == "project/billing-redesign/wp-a"


def test_scope_node_id_uses_type() -> None:
    initiative = Initiative(
        name="explore-ml-ranking",
        title="Explore ML Ranking",
        path="initiatives/explore-ml-ranking.md",
        introduction="",
        motivation="",
        detailed_description="",
    )
    project = Project(
        name="billing-redesign",
        title="Billing Redesign",
        path="projects/billing-redesign/billing-redesign.md",
        introduction="",
        motivation="",
        detailed_description="",
    )
    assert scope_node_id(initiative) == "initiative/explore-ml-ranking"
    assert scope_node_id(project) == "project/billing-redesign"


def test_resolve_entity_ref_unambiguous() -> None:
    roadmap = load(EXAMPLES)
    assert resolve_entity_ref(roadmap, "reduce-churn") == "goal/reduce-churn"
    assert resolve_entity_ref(roadmap, "missing-entity") == "missing-entity"


def test_resolve_entity_ref_ambiguous() -> None:
    roadmap = Roadmap(
        root="/tmp",
        initiatives=(
            Initiative(
                name="system-mci",
                title="System MCI",
                path="initiatives/system-mci.md",
                introduction="",
                motivation="",
                detailed_description="",
            ),
        ),
        goals=(
            Goal(
                name="system-mci",
                title="System MCI",
                path="goals/system-mci.md",
                description="TBD.",
            ),
        ),
    )
    with pytest.raises(ValueError, match="ambiguous dependency reference"):
        resolve_entity_ref(roadmap, "system-mci")


def test_is_legacy_flat_node_id() -> None:
    assert is_legacy_flat_node_id("goal", "reduce-churn")
    assert not is_legacy_flat_node_id("goal", "goal--reduce-churn")
    assert not is_legacy_flat_node_id("goal", "goal/reduce-churn")
    assert not is_legacy_flat_node_id("work_package", "billing-redesign--wp-a")


def test_registry_needs_id_migration() -> None:
    actual = {DesiredNode("goal", "reduce-churn")}
    desired = {DesiredNode("goal", "goal/reduce-churn")}
    assert registry_needs_id_migration(actual, desired)
    actual_dash = {DesiredNode("goal", "goal--reduce-churn")}
    assert registry_needs_id_migration(actual_dash, desired)


def test_validate_ambiguous_scope_dependency(tmp_path: Path) -> None:
    layout.ensure_roadmap_dirs(tmp_path)
    layout.create_goal(tmp_path, "system-mci")
    layout.create_initiative(tmp_path, "system-mci")
    initiative_path = layout.initiative_path(tmp_path, "system-mci")
    content = initiative_path.read_text(encoding="utf-8")
    initiative_path.write_text(
        content + "- after: system-mci [FS, Mandatory]\n",
        encoding="utf-8",
    )
    roadmap = load(tmp_path)
    result = validate_roadmap(roadmap)
    assert any("ambiguous dependency reference" in e.message for e in result.errors)
