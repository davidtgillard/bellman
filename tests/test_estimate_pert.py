"""Beta-PERT sampling tests."""

from __future__ import annotations

import random

import pytest

from bellman.estimate.pert import sample_beta_pert
from bellman.model import ThreePointEstimate
from bellman.report.wbs import pert_numeric


def test_sample_stays_within_bounds() -> None:
    estimate = ThreePointEstimate(1.0, 4.0, 10.0, "d")
    rng = random.Random(1)
    for _ in range(2000):
        value = sample_beta_pert(estimate, rng)
        assert estimate.optimistic <= value <= estimate.pessimistic


def test_degenerate_estimate_is_constant() -> None:
    estimate = ThreePointEstimate(3.0, 3.0, 3.0, "w")
    rng = random.Random(2)
    assert sample_beta_pert(estimate, rng) == 3.0


def test_large_n_mean_near_pert() -> None:
    estimate = ThreePointEstimate(1.0, 2.0, 7.0, "d")
    rng = random.Random(3)
    samples = [sample_beta_pert(estimate, rng) for _ in range(20_000)]
    assert sum(samples) / len(samples) == pytest.approx(
        pert_numeric(estimate), rel=0.03
    )
