"""FaultTimingRange / FaultSeverityRange and their resolvers."""

from __future__ import annotations

import random

import pytest

from backend.simulator.dataset.fault_variation import (
    FaultSeverityRange,
    FaultTimingRange,
    resolve_fault_severity,
    resolve_fault_start,
)

# --- FaultTimingRange bounds -------------------------------------------------


def test_negative_minimum_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultTimingRange(minimum_seconds=-1.0, maximum_seconds=100.0, step_seconds=10.0)


def test_non_positive_step_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultTimingRange(minimum_seconds=0.0, maximum_seconds=100.0, step_seconds=0.0)
    with pytest.raises(ValueError):
        FaultTimingRange(minimum_seconds=0.0, maximum_seconds=100.0, step_seconds=-5.0)


def test_maximum_below_minimum_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultTimingRange(minimum_seconds=100.0, maximum_seconds=50.0, step_seconds=10.0)


def test_valid_timing_range_constructs() -> None:
    FaultTimingRange(minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0)


def test_grid_values_covers_the_full_discrete_grid() -> None:
    grid = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
    ).grid_values()

    assert grid[0] == 90.0
    assert grid[-1] == 420.0
    assert len(grid) == 34  # (420 - 90) / 10 + 1
    assert list(grid) == sorted(grid)


def test_grid_values_stops_short_when_step_does_not_divide_evenly() -> None:
    grid = FaultTimingRange(
        minimum_seconds=0.0, maximum_seconds=25.0, step_seconds=10.0
    ).grid_values()

    assert grid == (0.0, 10.0, 20.0)
    assert max(grid) <= 25.0


def test_single_point_grid_is_valid() -> None:
    grid = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=90.0, step_seconds=10.0
    ).grid_values()

    assert grid == (90.0,)


def test_timing_range_json_round_trip() -> None:
    timing_range = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
    )
    restored = FaultTimingRange.from_json_dict(timing_range.to_json_dict())
    assert restored == timing_range


# --- FaultSeverityRange bounds -----------------------------------------------


def test_severity_minimum_at_zero_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultSeverityRange(minimum=0.0, maximum=1.0)


def test_severity_minimum_below_zero_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultSeverityRange(minimum=-0.1, maximum=1.0)


def test_severity_maximum_above_one_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultSeverityRange(minimum=0.5, maximum=1.5)


def test_severity_minimum_above_maximum_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultSeverityRange(minimum=0.8, maximum=0.2)


def test_valid_severity_range_constructs() -> None:
    FaultSeverityRange(minimum=0.15, maximum=1.0)


def test_severity_range_json_round_trip() -> None:
    severity_range = FaultSeverityRange(minimum=0.15, maximum=1.0)
    restored = FaultSeverityRange.from_json_dict(severity_range.to_json_dict())
    assert restored == severity_range


# --- resolve_fault_start ------------------------------------------------------


def test_resolve_fault_start_returns_fixed_value_unchanged() -> None:
    rng = random.Random("seed-a")
    result = resolve_fault_start(fixed=120.0, range_=None, rng=rng)
    assert result == 120.0


def test_resolve_fault_start_with_fixed_value_does_not_touch_rng() -> None:
    rng = random.Random(999)
    expected_next = random.Random(999).random()

    resolve_fault_start(fixed=120.0, range_=None, rng=rng)

    assert rng.random() == expected_next


def test_resolve_fault_start_none_stays_none_for_a_healthy_run() -> None:
    result = resolve_fault_start(fixed=None, range_=None, rng=random.Random("seed-a"))
    assert result is None


def test_resolve_fault_start_from_range_lands_on_the_grid() -> None:
    timing_range = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
    )
    grid = set(timing_range.grid_values())

    for seed in range(30):
        result = resolve_fault_start(
            fixed=None, range_=timing_range, rng=random.Random(seed)
        )
        assert result in grid


def test_resolve_fault_start_from_range_is_deterministic() -> None:
    timing_range = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
    )
    first = resolve_fault_start(
        fixed=None, range_=timing_range, rng=random.Random("seed-a")
    )
    second = resolve_fault_start(
        fixed=None, range_=timing_range, rng=random.Random("seed-a")
    )
    assert first == second


def test_resolve_fault_start_from_range_varies_across_seeds() -> None:
    timing_range = FaultTimingRange(
        minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
    )
    results = {
        resolve_fault_start(fixed=None, range_=timing_range, rng=random.Random(seed))
        for seed in range(30)
    }
    assert len(results) > 1


# --- resolve_fault_severity ---------------------------------------------------


def test_resolve_fault_severity_returns_fixed_value_unchanged() -> None:
    result = resolve_fault_severity(
        fixed=0.6, range_=None, rng=random.Random("seed-a")
    )
    assert result == 0.6


def test_resolve_fault_severity_fixed_none_defaults_to_zero() -> None:
    result = resolve_fault_severity(
        fixed=None, range_=None, rng=random.Random("seed-a")
    )
    assert result == 0.0


def test_resolve_fault_severity_with_fixed_value_does_not_touch_rng() -> None:
    rng = random.Random(999)
    expected_next = random.Random(999).random()

    resolve_fault_severity(fixed=0.6, range_=None, rng=rng)

    assert rng.random() == expected_next


def test_resolve_fault_severity_from_range_stays_within_bounds() -> None:
    severity_range = FaultSeverityRange(minimum=0.15, maximum=1.0)
    for seed in range(30):
        result = resolve_fault_severity(
            fixed=None, range_=severity_range, rng=random.Random(seed)
        )
        assert severity_range.minimum <= result <= severity_range.maximum


def test_resolve_fault_severity_from_range_is_deterministic() -> None:
    severity_range = FaultSeverityRange(minimum=0.15, maximum=1.0)
    first = resolve_fault_severity(
        fixed=None, range_=severity_range, rng=random.Random("seed-a")
    )
    second = resolve_fault_severity(
        fixed=None, range_=severity_range, rng=random.Random("seed-a")
    )
    assert first == second


def test_resolve_fault_severity_from_range_varies_across_seeds() -> None:
    severity_range = FaultSeverityRange(minimum=0.15, maximum=1.0)
    results = {
        resolve_fault_severity(
            fixed=None, range_=severity_range, rng=random.Random(seed)
        )
        for seed in range(30)
    }
    assert len(results) > 1
