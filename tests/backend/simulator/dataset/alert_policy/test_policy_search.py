"""Validation-only policy search and selection (PR170 spec section 10,
"Selection" test group)."""

from __future__ import annotations

import inspect

import numpy as np

from backend.simulator.dataset.alert_policy.policy_search import search_policies
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata

_CLASSES = ("cooling_degradation", "healthy")
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
    test-split data — its signature only accepts validation-shaped
    arguments plus the baseline latency scalar."""
    params = list(inspect.signature(search_policies).parameters)
    assert params == [
        "dataset",
        "val_mask",
        "proba",
        "classes",
        "baseline_median_latency_seconds",
    ]


def test_policies_missing_too_many_runs_are_rejected() -> None:
    """`MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS` is 1: missing 2 of 3
    fault runs must reject every candidate."""
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

    # run-1: always high-confidence cooling_degradation.
    # run-2, run-3: always healthy -> never detected under any candidate.
    proba = np.array([[0.95, 0.05]] * 5 + [[0.05, 0.95]] * 10)
    dataset = _build_dataset(run_ids, elapsed, y, run_metadata)
    mask = np.ones(15, dtype=bool)

    result = search_policies(
        dataset, mask, proba, _CLASSES, baseline_median_latency_seconds=None
    )

    assert all(c.rejected for c in result.candidates)
    assert result.all_rejected is True
    # Spec section 6: "If every policy either misses faults or fails to
    # reduce alert events, report that honestly" — no forced fallback.
    assert result.selected is None


def test_policies_exceeding_latency_tolerance_are_rejected() -> None:
    """A candidate whose median correct-class latency exceeds the
    baseline by more than the tolerance is rejected even with 0 missed
    runs."""
    run_metadata = {
        "run-1": RunMetadata(
            simulation_run_id="run-1", scenario_class_label="cooling_degradation",
            target_asset_id="asset-a", split="validation", configured_severity=0.8,
            fault_start_sim_seconds=0.0, fault_duration_sim_seconds=200.0,
        ),
    }
    # Confidence only reaches 0.5-0.6 late, forcing the highest entry
    # thresholds (0.7) to detect very slowly relative to the (artificially
    # tight) baseline.
    n = 20
    elapsed = _elapsed(n, start=0.0)
    y = ["cooling_degradation"] * n
    proba_rows = []
    for i in range(n):
        conf = 0.95 if i >= 15 else 0.55
        proba_rows.append([conf, 1.0 - conf])
    proba = np.array(proba_rows)
    dataset = _build_dataset(["run-1"] * n, elapsed, y, run_metadata)
    mask = np.ones(n, dtype=bool)

    result = search_policies(
        dataset, mask, proba, _CLASSES, baseline_median_latency_seconds=10.0
    )

    high_threshold_candidates = [
        c for c in result.candidates if c.config.entry_probability == 0.7
    ]
    assert any(c.rejected for c in high_threshold_candidates)


def test_deterministic_tie_breaking() -> None:
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

    result_a = search_policies(
        dataset, mask, proba, _CLASSES, baseline_median_latency_seconds=None
    )
    result_b = search_policies(
        dataset, mask, proba, _CLASSES, baseline_median_latency_seconds=None
    )

    assert result_a.selected is not None and result_b.selected is not None
    assert result_a.selected.config == result_b.selected.config
    assert [c.to_json_dict() for c in result_a.candidates] == [
        c.to_json_dict() for c in result_b.candidates
    ]
