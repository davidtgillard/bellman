"""Beta-PERT sampling for three-point duration estimates."""

from __future__ import annotations

import random

from bellman.model import ThreePointEstimate

_PERT_LAMBDA = 4.0


def sample_beta_pert(estimate: ThreePointEstimate, rng: random.Random) -> float:
    """Draw one duration from a Beta-PERT distribution.

    Uses shape parameters derived from the classic PERT mean
    ``(O + 4M + P) / 6``. When optimistic equals pessimistic the draw is
    deterministic.

    Args:
        estimate: Optimistic, most-likely, and pessimistic durations.
        rng: Seeded random generator.

    Returns:
        A duration in ``[optimistic, pessimistic]``.
    """
    low = estimate.optimistic
    high = estimate.pessimistic
    if high <= low:
        return low
    mean = (low + _PERT_LAMBDA * estimate.most_likely + high) / (_PERT_LAMBDA + 2.0)
    span = high - low
    alpha = (_PERT_LAMBDA + 2.0) * (mean - low) / span
    beta = (_PERT_LAMBDA + 2.0) * (high - mean) / span
    return low + span * rng.betavariate(alpha, beta)
