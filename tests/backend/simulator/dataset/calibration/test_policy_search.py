"""Policy search and selection (PR169 spec section 11, "Policy selection"
test group)."""

from __future__ import annotations

import inspect

import numpy as np

from backend.simulator.dataset.calibration.policy_search import search_policies
from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata

_DT = 10.0


def _elapsed(n: int, start: float = 0.0) -> list[float]:
    return [start + i * _DT for i in range(n)]


def _build_dataset(
    run_ids: list[str],
    elapsed: list[float],
    y: list[str],
    run_metadata: dict[str, RunMetadata],
) -> ExperimentDataset:
    n = len(run_ids)
    return ExperimentDataset(
        feature_columns=("stack_temperature",),
        X=np.zeros((n, 1)),
        y=np.array(y, dtype=object),
        split=np.array(["validation"] * n, dtype=object),
        run_ids=np.array(run_ids, dtype=object),
        asset_ids=np.array(["asset-a"] * n, dtype=object),
        timestamps=np.array([None] * n, dtype=object),
        elapsed_sim_seconds=np.array(elapsed, dtype=np.float64),
        fault_severity_row=np.full(n, np.nan),
        seconds_since_fault_start=np.full(n, np.nan),
        run_metadata=run_metadata,
        manifest={},
    )


def test_search_policies_signature_has_no_test_split_argument() -> None:
    """Structural leakage guard: `search_policies` cannot be called with
    test-split data at all — its signature only accepts a dataset, a
    validation-shaped boolean mask, and validation-shaped probabilities."""
    params = list(inspect.signature(search_policies).parameters)
    assert params == ["dataset", "val_mask", "proba", "class_order"]


def test_policies_missing_too_many_runs_are_rejected() -> None:
    """`MAX_MISSED_VALIDATION_FAULT_RUNS` is 1, so missing exactly 1 run
    is tolerated but missing 2 must reject every candidate."""
    classes = ("cooling_degradation", HEALTHY_LABEL)
    run_metadata = {
        f"run-{i}": RunMetadata(
            simulation_run_id=f"run-{i}", scenario_class_label="cooling_degradation",
            target_asset_id="asset-a", split="validation", configured_severity=0.8,
            fault_start_sim_seconds=0.0, fault_duration_sim_seconds=60.0,
        )
        for i in range(1, 4)
    }
    run_ids = ["run-1"] * 5 + ["run-2"] * 5 + ["run-3"] * 5
    elapsed = _elapsed(5, start=0.0) * 3
    y = ["cooling_degradation"] * 15

    # run-1: always predicted correctly and confidently.
    # run-2, run-3: always predicted healthy -> never detected at any
    # threshold, so every candidate misses 2 of 3 fault runs.
    proba = np.array([[0.95, 0.05]] * 5 + [[0.05, 0.95]] * 10)
    dataset = _build_dataset(run_ids, elapsed, y, run_metadata)
    mask = np.ones(15, dtype=bool)

    result = search_policies(dataset, mask, proba, classes)

    assert all(c.rejected for c in result.candidates)
    assert all(c.missed_run_count == 2 for c in result.candidates)
    # Selection still returns something (falls back to the full pool)
    # rather than raising.
    assert result.selected is not None


def test_tie_breaking_is_deterministic() -> None:
    classes = ("cooling_degradation", HEALTHY_LABEL)
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="cooling_degradation",
            target_asset_id="asset-a", split="validation", configured_severity=0.8,
            fault_start_sim_seconds=0.0, fault_duration_sim_seconds=60.0,
        ),
    }
    run_ids = ["run-1"] * 6
    elapsed = _elapsed(6, start=0.0)
    y = ["cooling_degradation"] * 6
    proba = np.array([[0.95, 0.05]] * 6)
    dataset = _build_dataset(run_ids, elapsed, y, run_metadata)
    mask = np.ones(6, dtype=bool)

    result_a = search_policies(dataset, mask, proba, classes)
    result_b = search_policies(dataset, mask, proba, classes)

    assert (
        result_a.selected.confidence_threshold == result_b.selected.confidence_threshold
    )
    assert (
        result_a.selected.persistence_samples == result_b.selected.persistence_samples
    )
    assert [c.to_json_dict() for c in result_a.candidates] == [
        c.to_json_dict() for c in result_b.candidates
    ]
