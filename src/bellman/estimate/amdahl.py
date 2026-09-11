"""Amdahl calendar-duration bound from effort and staffing."""

from __future__ import annotations


def amdahl_duration(
    effort: float, *, parallel_fraction: float, num_people: int
) -> float:
    """Return Amdahl's-law duration for total effort.

    Args:
        effort: Person-time (sum of leaf durations).
        parallel_fraction: Parallelizable fraction ``p`` in ``[0, 1]``.
        num_people: Staff count ``N`` (at least 1).

    Returns:
        ``effort * ((1 - p) + p / N)``.

    Raises:
        ValueError: When ``parallel_fraction`` is outside ``[0, 1]`` or
            ``num_people`` is less than 1.
    """
    if not 0.0 <= parallel_fraction <= 1.0:
        msg = f"parallel-fraction must be in [0, 1], got {parallel_fraction}"
        raise ValueError(msg)
    if num_people < 1:
        msg = f"num-people must be >= 1, got {num_people}"
        raise ValueError(msg)
    return effort * ((1.0 - parallel_fraction) + parallel_fraction / num_people)
