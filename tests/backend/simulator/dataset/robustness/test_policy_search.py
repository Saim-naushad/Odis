"""`search_robust_policies` specifications (spec sections 2, 4, 5).

Uses a small, real (physics-generated) dataset — mirrors `ood/conftest.py`'s
own `tiny_frozen_artifacts` rationale: at this scale a real pipeline still
produces genuine, non-degenerate probabilities, which a hand-built
`ExperimentDataset` would not, without the cost of the full 192-run robust
dataset.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np
import pytest

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.features.generate import generate_features
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.models.data import (
    ExperimentDataset,
    load_experiment_dataset,
)
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.models.selected_baseline import BASE_FEATURE_GROUP
from backend.simulator.dataset.ood.data_loading import (
    InsufficientDataSummary,
    filter_experiment_dataset,
    filter_insufficient_data_summary_to_runs,
    load_ood_experiment_dataset,
)
from backend.simulator.dataset.operating_conditions import OperatingConditionRanges
from backend.simulator.dataset.robustness.policy_search import search_robust_policies
from backend.simulator.dataset.run_config import DatasetScenario

_RUNS_PER_SCENARIO = 6
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)


class ValidationSplitFixture(NamedTuple):
    dataset: ExperimentDataset
    proba: np.ndarray
    class_order: tuple[str, ...]
    insufficient_data: InsufficientDataSummary


def _scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=_RUNS_PER_SCENARIO
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=150.0,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=150.0,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=150.0,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
    )


@pytest.fixture(scope="module")
def tiny_validation_split(
    tmp_path_factory: pytest.TempPathFactory,
) -> ValidationSplitFixture:
    root = tmp_path_factory.mktemp("policy-search")
    spec = DatasetSpec(
        dataset_id="policy-search-fixture",
        simulator_version="1.0.0",
        scenario_plans=_scenario_plans(),
        seeds=tuple(range(501, 501 + 4 * _RUNS_PER_SCENARIO)),
        target_asset_ids=("fuel-cell-stack-01",),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        run_start_time=_RUN_START,
        operating_condition_ranges=OperatingConditionRanges(),
        sensor_noise=(),
        split_proportions=SplitProportions(train=0.5, validation=0.5, test=0.0),
        output_directory=str(root / "dataset"),
    )
    dataset_result = generate_dataset(spec, generation_command="test")
    features_dir = root / "features"
    generate_features(
        dataset_result.output_directory, features_dir, generation_command="test"
    )

    dataset = load_experiment_dataset(features_dir, dataset_result.output_directory)
    train_mask = dataset.split_mask("train")
    pipeline = build_logistic_regression_pipeline(0.1)
    pipeline.fit(
        dataset.X_group(BASE_FEATURE_GROUP, train_mask), dataset.y[train_mask]
    )
    class_order = tuple(pipeline.named_steps["classifier"].classes_)

    full_dataset, insufficient = load_ood_experiment_dataset(
        features_dir, dataset_result.output_directory
    )
    val_mask = full_dataset.split_mask("validation")
    val_run_ids = set(full_dataset.run_ids[val_mask].tolist())
    val_dataset = filter_experiment_dataset(full_dataset, val_mask)
    val_insufficient = filter_insufficient_data_summary_to_runs(
        insufficient, val_run_ids, valid_row_count=len(val_dataset.y)
    )
    proba_val = pipeline.predict_proba(val_dataset.X_group(BASE_FEATURE_GROUP))
    return ValidationSplitFixture(val_dataset, proba_val, class_order, val_insufficient)


def test_search_evaluates_exactly_120_candidates(
    tiny_validation_split: ValidationSplitFixture,
) -> None:
    val_dataset, proba_val, class_order, val_insufficient = tiny_validation_split
    result = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        class_order,
        baseline_median_latency_seconds=None,
    )
    assert len(result.candidates) == 120


def test_search_is_deterministic(
    tiny_validation_split: ValidationSplitFixture,
) -> None:
    val_dataset, proba_val, class_order, val_insufficient = tiny_validation_split
    first = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        class_order,
        baseline_median_latency_seconds=None,
    )
    second = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        class_order,
        baseline_median_latency_seconds=None,
    )
    assert first.selected == second.selected
    assert [c.config for c in first.candidates] == [c.config for c in second.candidates]


def test_no_candidate_survives_an_impossible_latency_bound(
    tiny_validation_split: ValidationSplitFixture,
) -> None:
    """An unreachable baseline (0s, no tolerance headroom) rejects every
    candidate whose median latency is ever positive — the "no valid
    policy" case."""
    val_dataset, proba_val, class_order, val_insufficient = tiny_validation_split
    result = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        class_order,
        baseline_median_latency_seconds=-1000.0,
    )
    assert result.all_rejected
    assert result.selected is None
    assert all(c.rejected for c in result.candidates)


def test_selected_candidate_is_never_a_rejected_one(
    tiny_validation_split: ValidationSplitFixture,
) -> None:
    val_dataset, proba_val, class_order, val_insufficient = tiny_validation_split
    result = search_robust_policies(
        val_dataset,
        proba_val,
        val_insufficient,
        class_order,
        baseline_median_latency_seconds=None,
    )
    if result.selected is not None:
        assert not result.selected.rejected
