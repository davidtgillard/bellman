"""Monte Carlo project estimate: effort sum and Amdahl-limited duration."""

from __future__ import annotations

import random
from dataclasses import dataclass

from bellman.estimate.amdahl import amdahl_duration
from bellman.estimate.graph import build_estimate_graph
from bellman.estimate.pert import sample_beta_pert
from bellman.estimate.schedule import list_schedule_makespan
from bellman.model import Project

SCHEMA_VERSION = "1.0.0"
"""Semantic version of the project-estimate JSON document schema."""

DEFAULT_TRIALS = 10_000
"""Default number of Monte Carlo trials."""

DEFAULT_NUM_PEOPLE = 1
"""Default staff count (duration equals effort until staffing is raised)."""

DEFAULT_PARALLEL_FRACTION = 0.70
"""Default Amdahl parallelizable fraction."""

METHOD = "amdahl-cpm"
"""Combination method recorded in JSON output."""

SCHEDULER = "list-scheduling"
"""Staffed CPM scheduler recorded in JSON output."""

_INTERVALS: tuple[tuple[str, float, float], ...] = (
    ("68", 15.865, 84.135),
    ("95", 2.5, 97.5),
    ("99.7", 0.15, 99.85),
)


@dataclass(frozen=True, slots=True)
class Interval:
    """Two-sided percentile interval.

    Attributes:
        low: Lower percentile value.
        high: Upper percentile value.
    """

    low: float
    high: float


@dataclass(frozen=True, slots=True)
class SummaryStats:
    """Distribution summary for effort or duration.

    Attributes:
        mean: Arithmetic mean of trial values.
        median: 50th percentile of trial values.
        intervals: Confidence intervals keyed by ``68``, ``95``, and ``99.7``.
    """

    mean: float
    median: float
    intervals: dict[str, Interval]


@dataclass(frozen=True, slots=True)
class ProjectEstimate:
    """Project-level Monte Carlo estimate.

    Attributes:
        schema_version: JSON document schema version.
        project: Project natural name.
        unit: Shared duration unit.
        trials: Number of Monte Carlo trials.
        seed: RNG seed, or ``None`` when unspecified.
        num_people: Staff count used for duration.
        parallel_fraction: Amdahl parallelizable fraction.
        leaf_count: Number of estimated leaf work packages.
        method: Combination method identifier.
        scheduler: Scheduler identifier.
        effort: Person-time distribution.
        duration: Calendar-time distribution.
    """

    schema_version: str
    project: str
    unit: str
    trials: int
    seed: int | None
    num_people: int
    parallel_fraction: float
    leaf_count: int
    method: str
    scheduler: str
    effort: SummaryStats
    duration: SummaryStats


def _percentile(ordered: list[float], percent: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (percent / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _summarize(values: list[float]) -> SummaryStats:
    ordered = sorted(values)
    intervals = {
        name: Interval(low=_percentile(ordered, lo), high=_percentile(ordered, hi))
        for name, lo, hi in _INTERVALS
    }
    return SummaryStats(
        mean=sum(values) / len(values),
        median=_percentile(ordered, 50.0),
        intervals=intervals,
    )


def estimate_project(
    project: Project,
    *,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
    num_people: int = DEFAULT_NUM_PEOPLE,
    parallel_fraction: float = DEFAULT_PARALLEL_FRACTION,
) -> ProjectEstimate:
    """Run Monte Carlo effort and duration estimation for one project.

    Args:
        project: Project to estimate.
        trials: Number of simulation trials.
        seed: Optional RNG seed for reproducible draws.
        num_people: People available to work in parallel.
        parallel_fraction: Amdahl parallelizable fraction in ``[0, 1]``.

    Returns:
        Project estimate summaries for effort and duration.

    Raises:
        ValueError: When ``trials`` is less than 1, staffing or Amdahl
            parameters are invalid, or the project graph cannot be built.
    """
    if trials < 1:
        msg = f"trials must be >= 1, got {trials}"
        raise ValueError(msg)
    graph = build_estimate_graph(project)
    rng = random.Random(seed)
    efforts: list[float] = []
    durations: list[float] = []
    for _ in range(trials):
        sampled = {
            activity.activity_id: sample_beta_pert(activity.estimate, rng)
            for activity in graph.activities
        }
        effort = sum(sampled.values())
        makespan = list_schedule_makespan(
            sampled,
            graph.constraints,
            num_people=num_people,
        )
        calendar = amdahl_duration(
            effort,
            parallel_fraction=parallel_fraction,
            num_people=num_people,
        )
        efforts.append(effort)
        durations.append(max(makespan, calendar))
    return ProjectEstimate(
        schema_version=SCHEMA_VERSION,
        project=graph.project,
        unit=graph.unit,
        trials=trials,
        seed=seed,
        num_people=num_people,
        parallel_fraction=parallel_fraction,
        leaf_count=len(graph.activities),
        method=METHOD,
        scheduler=SCHEDULER,
        effort=_summarize(efforts),
        duration=_summarize(durations),
    )
