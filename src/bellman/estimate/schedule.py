"""Work-conserving list scheduling for staffed CPM."""

from __future__ import annotations

from dataclasses import dataclass

from bellman.estimate.graph import EstimateConstraint
from bellman.model import RelationType


@dataclass
class _Record:
    start: float
    duration: float
    logical_finish: float


def _earliest_start(
    activity_id: str,
    *,
    scheduled: dict[str, _Record],
    constraints: tuple[EstimateConstraint, ...],
) -> float | None:
    start = 0.0
    for edge in constraints:
        if edge.successor != activity_id:
            continue
        pred = scheduled.get(edge.predecessor)
        if edge.relation is RelationType.FS:
            if pred is None:
                return None
            start = max(start, pred.logical_finish)
        elif edge.relation is RelationType.SS:
            if pred is None:
                return None
            start = max(start, pred.start)
    return start


def _recompute_finishes(
    scheduled: dict[str, _Record],
    constraints: tuple[EstimateConstraint, ...],
) -> None:
    changed = True
    while changed:
        changed = False
        for activity_id, record in scheduled.items():
            finish = record.start + record.duration
            for edge in constraints:
                if edge.successor != activity_id:
                    continue
                pred = scheduled.get(edge.predecessor)
                if pred is None:
                    continue
                if edge.relation is RelationType.FF:
                    finish = max(finish, pred.logical_finish)
                elif edge.relation is RelationType.SF:
                    finish = max(finish, pred.start)
            if finish > record.logical_finish:
                record.logical_finish = finish
                changed = True


def list_schedule_makespan(
    durations: dict[str, float],
    constraints: tuple[EstimateConstraint, ...],
    *,
    num_people: int,
) -> float:
    """Return calendar makespan from list scheduling.

    When a person is free and a leaf is precedence-ready, it starts. FS and SS
    constrain start; FF and SF may extend logical finish after the worker is
    released.

    Args:
        durations: Sampled duration for each activity id.
        constraints: Expanded leaf-to-leaf precedence constraints.
        num_people: Number of people who can work at once.

    Returns:
        Makespan (maximum logical finish).

    Raises:
        ValueError: When ``num_people`` is less than 1 or remaining work
            cannot be started (for example a cycle missed earlier).
    """
    if num_people < 1:
        msg = f"num-people must be >= 1, got {num_people}"
        raise ValueError(msg)
    if not durations:
        return 0.0

    remaining = set(durations)
    scheduled: dict[str, _Record] = {}
    active: list[tuple[float, str]] = []
    time = 0.0
    busy = 0

    while remaining or active:
        while busy < num_people:
            candidates: list[tuple[str, float]] = []
            for activity_id in remaining:
                earliest = _earliest_start(
                    activity_id,
                    scheduled=scheduled,
                    constraints=constraints,
                )
                if earliest is not None and earliest <= time:
                    candidates.append((activity_id, earliest))
            if not candidates:
                break
            activity_id, _ = min(candidates, key=lambda item: item[0])
            duration = durations[activity_id]
            scheduled[activity_id] = _Record(
                start=time,
                duration=duration,
                logical_finish=time + duration,
            )
            remaining.remove(activity_id)
            active.append((time + duration, activity_id))
            busy += 1
            _recompute_finishes(scheduled, constraints)

        if not remaining and not active:
            break

        next_times: list[float] = [finish for finish, _ in active]
        if busy < num_people:
            for activity_id in remaining:
                earliest = _earliest_start(
                    activity_id,
                    scheduled=scheduled,
                    constraints=constraints,
                )
                if earliest is not None and earliest > time:
                    next_times.append(earliest)
        if not next_times:
            msg = "cannot schedule remaining work packages"
            raise ValueError(msg)
        time = min(next_times)
        still_active: list[tuple[float, str]] = []
        for finish, activity_id in active:
            if finish <= time:
                busy -= 1
            else:
                still_active.append((finish, activity_id))
        active = still_active

    return max(record.logical_finish for record in scheduled.values())
