"""Shared fixtures for PR164 dataset-generation tests, and (from PR168/169
onward) the small real feature-dataset fixture shared by every model/
calibration test suite under this directory."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest
import threadpoolctl

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.features.generate import generate_features
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.operating_conditions import (
    NoiseRegime,
    OperatingConditionRanges,
    SensorNoiseConfig,
)
from backend.simulator.dataset.run_config import DatasetScenario

DEFAULT_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)

# What `spec_factory` (below) yields: a keyword-only builder for a valid
# `DatasetSpec`, with sensible defaults for every field a given test
# doesn't care about overriding.
SpecFactory = Callable[..., DatasetSpec]


def default_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=2,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=1.0,
        ),
    )


@pytest.fixture
def spec_factory(tmp_path: Path) -> SpecFactory:
    def _make(
        *,
        dataset_id: str = "test-dataset",
        scenario_plans: tuple[ScenarioRunSpec, ...] | None = None,
        seeds: tuple[int, ...] | None = None,
        target_asset_ids: tuple[str, ...] = (
            "fuel-cell-stack-01",
            "fuel-cell-stack-02",
        ),
        duration_sim_seconds: float = 300.0,
        dt_seconds: float = 30.0,
        run_start_time: datetime = DEFAULT_RUN_START,
        operating_condition_ranges: OperatingConditionRanges | None = None,
        sensor_noise: tuple[SensorNoiseConfig, ...] = (),
        sensor_noise_regimes: tuple[NoiseRegime, ...] = (),
        split_proportions: SplitProportions | None = None,
        output_directory: str | None = None,
    ) -> DatasetSpec:
        plans = (
            scenario_plans if scenario_plans is not None else default_scenario_plans()
        )
        total = sum(plan.run_count for plan in plans)
        resolved_seeds = seeds if seeds is not None else tuple(range(1, total + 1))
        return DatasetSpec(
            dataset_id=dataset_id,
            simulator_version="1.0.0",
            scenario_plans=plans,
            seeds=resolved_seeds,
            target_asset_ids=target_asset_ids,
            duration_sim_seconds=duration_sim_seconds,
            dt_seconds=dt_seconds,
            run_start_time=run_start_time,
            operating_condition_ranges=(
                operating_condition_ranges or OperatingConditionRanges()
            ),
            sensor_noise=sensor_noise,
            sensor_noise_regimes=sensor_noise_regimes,
            split_proportions=(
                split_proportions
                or SplitProportions(train=0.5, validation=0.25, test=0.25)
            ),
            output_directory=str(output_directory or (tmp_path / "output")),
        )

    return _make


@pytest.fixture(autouse=True)
def _single_threaded_fitting() -> Iterator[None]:
    """Test-only performance fixture.

    `HistGradientBoostingClassifier` nests two layers of parallelism: an
    outer joblib worker pool around its binning step, and an inner OpenMP
    thread pool (8 threads here) used by each worker's own histogram
    Cython code. On a real multi-thousand-row training set the resulting
    oversubscription is a rounding error; on these tests' deliberately
    tiny fixtures (a handful of rows) it made a single fit take seconds of
    pure thread-contention overhead instead of milliseconds. Pinning both
    layers to one thread here only affects *this test session* — the CLI
    and library code make no such choice, so production runs keep
    scikit-learn's own defaults.
    """
    with joblib.parallel_backend("threading"), threadpoolctl.threadpool_limits(1):
        yield


_FEATURES_FIXTURE_FAULT_START = 150.0
_FEATURES_FIXTURE_FAULT_DURATION = 60.0
_FEATURES_FIXTURE_FAULT_SEVERITY = 1.0
_FEATURES_FIXTURE_RUNS_PER_SCENARIO = 4


def _four_class_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION,
            run_count=_FEATURES_FIXTURE_RUNS_PER_SCENARIO,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_FEATURES_FIXTURE_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FEATURES_FIXTURE_FAULT_START,
            fault_duration_sim_seconds=_FEATURES_FIXTURE_FAULT_DURATION,
            fault_severity=_FEATURES_FIXTURE_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_FEATURES_FIXTURE_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FEATURES_FIXTURE_FAULT_START,
            fault_duration_sim_seconds=_FEATURES_FIXTURE_FAULT_DURATION,
            fault_severity=_FEATURES_FIXTURE_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_FEATURES_FIXTURE_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FEATURES_FIXTURE_FAULT_START,
            fault_duration_sim_seconds=_FEATURES_FIXTURE_FAULT_DURATION,
            fault_severity=_FEATURES_FIXTURE_FAULT_SEVERITY,
        ),
    )


@pytest.fixture
def tiny_features_dir(tmp_path: Path, spec_factory: SpecFactory) -> tuple[Path, Path]:
    """A small, real (physics-produced) feature dataset shared by the
    PR168 `models` and PR169 `calibration` test suites: 4 runs per class
    on a single target asset. Under the default 0.5/0.25/0.25 split
    proportions that divides evenly into 2 train / 1 validation / 1 test
    run per class, so every split exercises every class without depending
    on shuffling luck. Returns `(features_dir, dataset_dir)`."""
    spec = spec_factory(
        dataset_id="models-fixture",
        scenario_plans=_four_class_scenario_plans(),
        seeds=tuple(range(301, 301 + 4 * _FEATURES_FIXTURE_RUNS_PER_SCENARIO)),
        target_asset_ids=("fuel-cell-stack-01",),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        output_directory=str(tmp_path / "dataset"),
    )
    dataset_result = generate_dataset(spec, generation_command="test")
    features_dir = tmp_path / "features"
    generate_features(
        dataset_result.output_directory, features_dir, generation_command="test"
    )
    return features_dir, dataset_result.output_directory
