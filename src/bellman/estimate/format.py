"""Plaintext and JSON rendering of a project estimate."""

from __future__ import annotations

import json
from typing import Any

from bellman.estimate.simulate import SCHEMA_VERSION, ProjectEstimate, SummaryStats


def _format_amount(value: float, unit: str) -> str:
    return f"{value:.2f}{unit}"


def _format_interval(stats: SummaryStats, name: str, unit: str) -> str:
    interval = stats.intervals[name]
    return f"{_format_amount(interval.low, unit)}–{_format_amount(interval.high, unit)}"


def format_estimate_text(estimate: ProjectEstimate) -> str:
    """Render a human-readable estimate summary.

    Args:
        estimate: Completed project estimate.

    Returns:
        Multiline plaintext report.
    """
    unit = estimate.unit
    seed_line = f"Seed: {estimate.seed}\n" if estimate.seed is not None else ""
    return (
        f"Project: {estimate.project}\n"
        f"Trials: {estimate.trials}\n"
        f"{seed_line}"
        f"Num people: {estimate.num_people}\n"
        f"Parallel fraction: {estimate.parallel_fraction:.2f}\n"
        f"Unit: {unit}\n"
        f"\n"
        f"Expected effort:   {_format_amount(estimate.effort.mean, unit)}\n"
        f"Effort median:     {_format_amount(estimate.effort.median, unit)}\n"
        f"68% effort CI:     {_format_interval(estimate.effort, '68', unit)}\n"
        f"95% effort CI:     {_format_interval(estimate.effort, '95', unit)}\n"
        f"99.7% effort CI:   {_format_interval(estimate.effort, '99.7', unit)}\n"
        f"\n"
        f"Expected duration: {_format_amount(estimate.duration.mean, unit)}\n"
        f"Duration median:   {_format_amount(estimate.duration.median, unit)}\n"
        f"68% duration CI:    {_format_interval(estimate.duration, '68', unit)}\n"
        f"95% duration CI:    {_format_interval(estimate.duration, '95', unit)}\n"
        f"99.7% duration CI:  {_format_interval(estimate.duration, '99.7', unit)}\n"
    )


def _stats_payload(stats: SummaryStats) -> dict[str, Any]:
    return {
        "mean": stats.mean,
        "median": stats.median,
        "intervals": {
            name: {"low": interval.low, "high": interval.high}
            for name, interval in stats.intervals.items()
        },
    }


def estimate_to_dict(estimate: ProjectEstimate) -> dict[str, Any]:
    """Convert an estimate to the versioned JSON document.

    Args:
        estimate: Completed project estimate.

    Returns:
        JSON-serializable mapping matching schema ``SCHEMA_VERSION``.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "project": estimate.project,
        "unit": estimate.unit,
        "trials": estimate.trials,
        "seed": estimate.seed,
        "num_people": estimate.num_people,
        "parallel_fraction": estimate.parallel_fraction,
        "leaf_count": estimate.leaf_count,
        "method": estimate.method,
        "scheduler": estimate.scheduler,
        "effort": _stats_payload(estimate.effort),
        "duration": _stats_payload(estimate.duration),
    }


def format_estimate_json(estimate: ProjectEstimate) -> str:
    """Render a machine-readable estimate document.

    Args:
        estimate: Completed project estimate.

    Returns:
        JSON text with a trailing newline.
    """
    return json.dumps(estimate_to_dict(estimate), indent=2) + "\n"
