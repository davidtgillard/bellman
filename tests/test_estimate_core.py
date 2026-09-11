"""Amdahl, graph, schedule, and simulate tests."""

from __future__ import annotations

from typing import Literal

import pytest

from bellman.estimate.amdahl import amdahl_duration
from bellman.estimate.graph import EstimateConstraint, build_estimate_graph
from bellman.estimate.schedule import list_schedule_makespan
from bellman.estimate.simulate import _percentile, estimate_project
from bellman.model import (
    UNKNOWN_ESTIMATE,
    Hardness,
    PrecedenceEdge,
    Project,
    RelationType,
    ThreePointEstimate,
    WorkPackage,
)


def _project(*packages: WorkPackage, name: str = "demo") -> Project:
    return Project(
        name=name,
        title="Demo",
        path=f"projects/{name}/{name}.md",
        introduction="intro",
        motivation="why",
        detailed_description="detail",
        criteria_for_success="done",
        work_packages=packages,
    )


def _leaf(
    slug: str,
    amount: float,
    *,
    unit: Literal["h", "d", "w"] = "w",
    predecessor: str | None = None,
    relation: RelationType = RelationType.FS,
) -> WorkPackage:
    deps: tuple[PrecedenceEdge, ...] = ()
    if predecessor is not None:
        deps = (
            PrecedenceEdge(
                predecessor=predecessor,
                successor=f"demo/{slug}",
                relation=relation,
                hardness=Hardness.MANDATORY,
            ),
        )
    return WorkPackage(
        slug=slug,
        title=slug,
        description="work",
        estimate=ThreePointEstimate(amount, amount, amount, unit),
        dependencies=deps,
    )


def test_amdahl_formula() -> None:
    assert amdahl_duration(10.0, parallel_fraction=0.70, num_people=2) == pytest.approx(
        6.5
    )


def test_amdahl_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="parallel-fraction"):
        amdahl_duration(10.0, parallel_fraction=1.5, num_people=1)
    with pytest.raises(ValueError, match="num-people"):
        amdahl_duration(10.0, parallel_fraction=0.7, num_people=0)


def test_effort_is_sum_regardless_of_staffing() -> None:
    project = _project(_leaf("a", 5.0), _leaf("b", 5.0))
    for num_people, parallel_fraction in ((1, 0.70), (2, 0.70), (2, 1.0)):
        result = estimate_project(
            project,
            trials=8,
            seed=1,
            num_people=num_people,
            parallel_fraction=parallel_fraction,
        )
        assert result.effort.mean == pytest.approx(10.0)
        assert result.effort.median == pytest.approx(10.0)


def test_amdahl_defaults_duration_equals_effort() -> None:
    project = _project(_leaf("a", 3.0), _leaf("b", 4.0))
    result = estimate_project(project, trials=5, seed=1)
    assert result.duration.mean == pytest.approx(result.effort.mean)


def test_amdahl_unlinked_two_people() -> None:
    project = _project(_leaf("a", 5.0), _leaf("b", 5.0))
    result = estimate_project(
        project,
        trials=5,
        seed=1,
        num_people=2,
        parallel_fraction=0.70,
    )
    assert result.duration.mean == pytest.approx(6.5)


def test_amdahl_perfect_parallel_uses_schedule_max() -> None:
    project = _project(_leaf("a", 5.0), _leaf("b", 5.0))
    result = estimate_project(
        project,
        trials=5,
        seed=1,
        num_people=2,
        parallel_fraction=1.0,
    )
    assert result.duration.mean == pytest.approx(5.0)


def test_qualified_in_project_predecessor() -> None:
    graph = build_estimate_graph(
        _project(_leaf("a", 1.0), _leaf("b", 1.0, predecessor="demo/a"))
    )
    assert graph.constraints == (
        EstimateConstraint("demo/a", "demo/b", RelationType.FS),
    )
    with pytest.raises(ValueError, match="outside project"):
        build_estimate_graph(
            _project(_leaf("a", 1.0), _leaf("b", 1.0, predecessor="demo/ghost"))
        )


def test_fs_duration_is_sum() -> None:
    project = _project(
        _leaf("a", 5.0),
        _leaf("b", 5.0, predecessor="a"),
    )
    result = estimate_project(
        project,
        trials=5,
        seed=1,
        num_people=4,
        parallel_fraction=0.70,
    )
    assert result.duration.mean == pytest.approx(10.0)
    assert result.effort.mean == pytest.approx(10.0)


def test_list_schedule_fs_and_unlinked() -> None:
    fs = (EstimateConstraint("demo/a", "demo/b", RelationType.FS),)
    assert (
        list_schedule_makespan(
            {"demo/a": 10.0, "demo/b": 2.0},
            fs,
            num_people=8,
        )
        == 12.0
    )
    assert (
        list_schedule_makespan(
            {"demo/a": 5.0, "demo/b": 5.0},
            (),
            num_people=1,
        )
        == 10.0
    )
    assert (
        list_schedule_makespan(
            {"demo/a": 5.0, "demo/b": 5.0},
            (),
            num_people=2,
        )
        == 5.0
    )


def test_list_schedule_ff_and_ss() -> None:
    ff = (EstimateConstraint("demo/a", "demo/b", RelationType.FF),)
    ss = (EstimateConstraint("demo/a", "demo/b", RelationType.SS),)
    assert (
        list_schedule_makespan({"demo/a": 10.0, "demo/b": 2.0}, ff, num_people=2)
        == 10.0
    )
    assert (
        list_schedule_makespan({"demo/a": 10.0, "demo/b": 2.0}, ss, num_people=2)
        == 10.0
    )
    assert (
        list_schedule_makespan(
            {"demo/a": 2.0, "demo/z": 10.0},
            (EstimateConstraint("demo/z", "demo/a", RelationType.FF),),
            num_people=2,
        )
        == 10.0
    )


def test_list_schedule_sf_and_empty() -> None:
    sf = (EstimateConstraint("demo/a", "demo/b", RelationType.SF),)
    assert (
        list_schedule_makespan({"demo/a": 10.0, "demo/b": 2.0}, sf, num_people=2)
        == 10.0
    )
    assert list_schedule_makespan({}, (), num_people=1) == 0.0


def test_list_schedule_rejects_zero_people() -> None:
    with pytest.raises(ValueError, match="num-people"):
        list_schedule_makespan({"demo/a": 1.0}, (), num_people=0)


def test_list_schedule_deadlock() -> None:
    with pytest.raises(ValueError, match="cannot schedule"):
        list_schedule_makespan(
            {"demo/b": 1.0},
            (EstimateConstraint("demo/a", "demo/b", RelationType.FS),),
            num_people=1,
        )


def test_build_graph_rejects_empty_unknown_mixed_and_cross_project() -> None:
    with pytest.raises(ValueError, match="no work packages"):
        build_estimate_graph(_project())
    with pytest.raises(ValueError, match="unknown estimate"):
        build_estimate_graph(
            _project(
                WorkPackage(
                    slug="a",
                    title="a",
                    description="d",
                    estimate=UNKNOWN_ESTIMATE,
                )
            )
        )
    with pytest.raises(ValueError, match="missing estimate"):
        build_estimate_graph(
            _project(WorkPackage(slug="a", title="a", description="d"))
        )
    with pytest.raises(ValueError, match="mixed duration units"):
        build_estimate_graph(
            _project(_leaf("a", 1.0, unit="d"), _leaf("b", 1.0, unit="w"))
        )
    with pytest.raises(ValueError, match="cross-project"):
        build_estimate_graph(
            _project(_leaf("a", 1.0), _leaf("b", 1.0, predecessor="other/wp"))
        )
    with pytest.raises(ValueError, match="outside project"):
        build_estimate_graph(
            _project(_leaf("a", 1.0), _leaf("b", 1.0, predecessor="ghost"))
        )


def test_cycle_is_rejected() -> None:
    with pytest.raises(ValueError, match="precedence cycle"):
        build_estimate_graph(
            _project(
                _leaf("a", 1.0, predecessor="b"),
                _leaf("b", 1.0, predecessor="a"),
            )
        )


def test_parent_successor_inherits_constraint() -> None:
    child_a = _leaf("child-a", 2.0)
    child_b = _leaf("child-b", 3.0)
    parent = WorkPackage(
        slug="group",
        title="group",
        description="group",
        sub_packages=(child_a, child_b),
        dependencies=(
            PrecedenceEdge(
                predecessor="setup",
                successor="demo/group",
                relation=RelationType.FS,
                hardness=Hardness.MANDATORY,
            ),
        ),
    )
    graph = build_estimate_graph(_project(_leaf("setup", 1.0), parent))
    successors = {edge.successor for edge in graph.constraints}
    assert successors == {"demo/child-a", "demo/child-b"}
    assert all(edge.predecessor == "demo/setup" for edge in graph.constraints)


def test_parent_dependency_does_not_self_loop() -> None:
    child = _leaf("child", 2.0, predecessor="parent")
    parent = WorkPackage(
        slug="parent",
        title="parent",
        description="group",
        sub_packages=(child,),
    )
    graph = build_estimate_graph(_project(parent))
    assert len(graph.activities) == 1
    assert graph.constraints == ()


def test_seed_reproducible() -> None:
    project = _project(
        WorkPackage(
            slug="skew",
            title="skew",
            description="d",
            estimate=ThreePointEstimate(1.0, 2.0, 8.0, "w"),
        )
    )
    first = estimate_project(project, trials=50, seed=11)
    second = estimate_project(project, trials=50, seed=11)
    assert first.effort.mean == second.effort.mean
    assert first.duration.mean == second.duration.mean


def test_estimate_rejects_bad_trials() -> None:
    with pytest.raises(ValueError, match="trials"):
        estimate_project(_project(_leaf("a", 1.0)), trials=0)


def test_percentile_empty_and_single() -> None:
    assert _percentile([], 50.0) == 0.0
    assert _percentile([4.0], 99.7) == 4.0


def test_single_trial_estimate() -> None:
    result = estimate_project(_project(_leaf("a", 3.0)), trials=1, seed=1)
    assert result.effort.mean == pytest.approx(3.0)
    assert result.effort.intervals["68"].low == pytest.approx(3.0)


def test_successor_must_exist() -> None:
    rogue = WorkPackage(
        slug="a",
        title="a",
        description="d",
        estimate=ThreePointEstimate(1.0, 1.0, 1.0, "w"),
        dependencies=(
            PrecedenceEdge(
                predecessor="a",
                successor="demo/missing",
                relation=RelationType.FS,
                hardness=Hardness.MANDATORY,
            ),
        ),
    )
    with pytest.raises(ValueError, match="successor"):
        build_estimate_graph(_project(rogue))


def test_bare_successor_uses_owner_slug() -> None:
    edge = PrecedenceEdge(
        predecessor="a",
        successor="b",
        relation=RelationType.FS,
        hardness=Hardness.MANDATORY,
    )
    graph = build_estimate_graph(
        _project(
            _leaf("a", 1.0),
            WorkPackage(
                slug="b",
                title="b",
                description="d",
                estimate=ThreePointEstimate(1.0, 1.0, 1.0, "w"),
                dependencies=(edge,),
            ),
        )
    )
    assert graph.constraints == (
        EstimateConstraint("demo/a", "demo/b", RelationType.FS),
    )
