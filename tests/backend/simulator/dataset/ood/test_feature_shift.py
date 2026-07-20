"""Feature-distribution shift measures (spec section 14, "Feature shift").

Uses directly-constructed `ExperimentDataset`s (not a full generated
dataset) so the shift arithmetic itself is pinned independently of the
physics simulator.
"""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.feature_shift import compute_feature_shift

_COLUMNS = (
    "stack_temperature",  # raw
    "stack_temperature__diff_10s",  # temporal
    "voltage_per_current",  # cross_signal
    "voltage__healthy_residual",  # residual
    "current",  # raw, held constant across both cohorts
)


def _dataset(x: np.ndarray) -> ExperimentDataset:
    n = x.shape[0]
    return ExperimentDataset(
        feature_columns=_COLUMNS,
        X=x,
        y=np.array(["healthy"] * n, dtype=object),
        split=np.array(["train"] * n, dtype=object),
        run_ids=np.array([f"run-{i}" for i in range(n)], dtype=object),
        asset_ids=np.array(["asset-01"] * n, dtype=object),
        timestamps=np.array([0] * n, dtype=object),
        elapsed_sim_seconds=np.zeros(n, dtype=np.float64),
        fault_severity_row=np.full(n, np.nan, dtype=np.float64),
        seconds_since_fault_start=np.full(n, np.nan, dtype=np.float64),
        run_metadata={},
        manifest={},
    )


def test_zero_shift_for_identical_distributions() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(50, len(_COLUMNS)))
    train = _dataset(x)
    ood = _dataset(x.copy())

    report = compute_feature_shift(train, ood)

    for entry in report.entries.values():
        assert entry.standardized_mean_difference == 0.0
        assert entry.wasserstein_distance == 0.0
        assert entry.ood_out_of_range_fraction == 0.0


def test_positive_shift_for_shifted_distributions() -> None:
    rng = np.random.default_rng(1)
    train_x = rng.normal(loc=0.0, scale=1.0, size=(200, len(_COLUMNS)))
    ood_x = rng.normal(loc=5.0, scale=1.0, size=(200, len(_COLUMNS)))
    train = _dataset(train_x)
    ood = _dataset(ood_x)

    report = compute_feature_shift(train, ood)

    for entry in report.entries.values():
        assert entry.standardized_mean_difference > 3.0
        assert entry.wasserstein_distance > 3.0
        assert entry.ood_out_of_range_fraction > 0.85


def test_stable_behavior_for_a_constant_feature() -> None:
    n = 30
    x = np.zeros((n, len(_COLUMNS)))
    x[:, -1] = 7.0  # "current" held constant in both cohorts
    train = _dataset(x)
    ood = _dataset(x.copy())

    report = compute_feature_shift(train, ood)

    constant_entry = report.entries["current"]
    assert constant_entry.standardized_mean_difference == 0.0
    assert np.isfinite(constant_entry.standardized_mean_difference)

    ood_shifted = x.copy()
    ood_shifted[:, -1] = 8.0
    report_shifted = compute_feature_shift(train, _dataset(ood_shifted))
    shifted_entry = report_shifted.entries["current"]
    # Zero pooled std falls back to the raw mean difference rather than
    # dividing by zero.
    assert shifted_entry.standardized_mean_difference == 1.0
    assert np.isfinite(shifted_entry.standardized_mean_difference)


def test_deterministic_rankings() -> None:
    rng = np.random.default_rng(2)
    train_x = rng.normal(size=(80, len(_COLUMNS)))
    ood_x = rng.normal(size=(80, len(_COLUMNS))) + rng.normal(
        size=len(_COLUMNS)
    )
    train = _dataset(train_x)
    ood = _dataset(ood_x)

    first = [e.name for e in compute_feature_shift(train, ood).ranked()]
    second = [e.name for e in compute_feature_shift(train, ood).ranked()]
    assert first == second

    by_group = [e.name for e in compute_feature_shift(train, ood).ranked("raw")]
    assert all(
        compute_feature_shift(train, ood).entries[name].group == "raw"
        for name in by_group
    )
