"""Shared fixtures for PR168 model-experiment tests.

`tiny_features_dir` generates one small, real (physics-produced) dataset —
the same technique `tests/.../features/conftest.py`'s `tiny_dataset_dir_10s`
uses — with 4 runs per class on a single target asset. Under the default
0.5/0.25/0.25 split proportions that divides evenly into 2 train / 1
validation / 1 test run per class, so every split exercises every class
without depending on shuffling luck.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import joblib
import pytest
import threadpoolctl

from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
from backend.simulator.dataset.features.generate import generate_features
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.run_config import DatasetScenario

from ..conftest import SpecFactory


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

_FAULT_START = 150.0
_FAULT_DURATION = 60.0
_FAULT_SEVERITY = 1.0
_RUNS_PER_SCENARIO = 4


def _four_class_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=_RUNS_PER_SCENARIO
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
    )


@pytest.fixture
def tiny_features_dir(tmp_path: Path, spec_factory: SpecFactory) -> tuple[Path, Path]:
    """Returns `(features_dir, dataset_dir)`."""
    spec = spec_factory(
        dataset_id="models-fixture",
        scenario_plans=_four_class_scenario_plans(),
        seeds=tuple(range(301, 301 + 4 * _RUNS_PER_SCENARIO)),
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
