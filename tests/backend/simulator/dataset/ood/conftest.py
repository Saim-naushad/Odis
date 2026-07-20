"""Shared fixtures for PR171 OOD-evaluation tests: a tiny real (physics-
produced) pair of "training" and "OOD-like" datasets, plus tiny frozen
model/alert-policy artifacts fit on the training one.

The model artifact is written directly with the frozen PR168 baseline
(logistic regression, feature group D, `C=0.01`) rather than via
`models.generate.generate_models`'s own ablation — on a dataset this
tiny, that ablation's own validation-based selection is not guaranteed to
land on the same baseline the production pilot dataset selected (it can,
and did during development, pick histogram gradient boosting instead),
which would make every "this is a compatible frozen artifact" test
fixture-dependent rather than a real test of `ood.artifacts`. Writing the
baseline directly keeps these tests about the OOD module, not about what
a tiny ablation happens to prefer, and is substantially cheaper than a
full 8-candidate ablation besides. `generate_alert_policy` is used as-is:
it already always fits the frozen baseline internally regardless of what
`generate_models` would have selected (see `alert_policy/experiment.py`).

Both fixtures are module-scoped — this module's tests only ever read
from, never mutate in place, the directories these fixtures return
(corruption tests copy into a fresh `tmp_path` first). Because a
module-scoped fixture cannot depend on function-scoped `tmp_path`/
`spec_factory`, both fixtures build their own `DatasetSpec` directly via
`tmp_path_factory` rather than reusing the parent conftest's
function-scoped helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest

from backend.simulator.dataset.alert_policy.generate import generate_alert_policy
from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.features.generate import generate_features
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.manifest import resolve_git_commit
from backend.simulator.dataset.models.config import MODEL_SCHEMA_VERSION, RANDOM_SEED
from backend.simulator.dataset.models.data import load_experiment_dataset
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.models.selected_baseline import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
)
from backend.simulator.dataset.operating_conditions import (
    OperatingConditionRanges,
    SensorNoiseConfig,
)
from backend.simulator.dataset.run_config import DatasetScenario

_FAULT_DURATION = 60.0
_FAULT_SEVERITY = 1.0
_RUNS_PER_SCENARIO = 4
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)


def _four_class_scenario_plans(*, fault_start: float) -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION,
            run_count=_RUNS_PER_SCENARIO,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
    )


def _build_features(
    output_root: Path,
    *,
    dataset_id: str,
    fault_start: float,
    seeds: tuple[int, ...],
    operating_condition_ranges: OperatingConditionRanges,
    sensor_noise: tuple[SensorNoiseConfig, ...],
) -> tuple[Path, Path]:
    spec = DatasetSpec(
        dataset_id=dataset_id,
        simulator_version="1.0.0",
        scenario_plans=_four_class_scenario_plans(fault_start=fault_start),
        seeds=seeds,
        target_asset_ids=("fuel-cell-stack-01",),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        run_start_time=_RUN_START,
        operating_condition_ranges=operating_condition_ranges,
        sensor_noise=sensor_noise,
        split_proportions=SplitProportions(train=0.5, validation=0.25, test=0.25),
        output_directory=str(output_root / "dataset"),
    )
    dataset_result = generate_dataset(spec, generation_command="test")
    features_dir = output_root / "features"
    generate_features(
        dataset_result.output_directory, features_dir, generation_command="test"
    )
    return features_dir, dataset_result.output_directory


def _write_frozen_model_artifact(
    features_dir: Path, dataset_dir: Path, models_dir: Path
) -> None:
    """Fit and serialize exactly the frozen PR168 baseline (logistic
    regression, feature group D, `C=0.01`) — see module docstring for why
    this bypasses `models.generate.generate_models`'s own ablation."""
    dataset = load_experiment_dataset(features_dir, dataset_dir)
    train_mask = dataset.split_mask("train")
    pipeline = build_logistic_regression_pipeline(BASE_LOGISTIC_REGRESSION_C)
    pipeline.fit(dataset.X_group(BASE_FEATURE_GROUP, train_mask), dataset.y[train_mask])

    artifacts_dir = models_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    joblib.dump(pipeline, artifacts_dir / "selected_pipeline.joblib")

    git_commit, git_status = resolve_git_commit()
    metadata = {
        "model_schema_version": MODEL_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git_commit_status": git_status,
        "random_seed": RANDOM_SEED,
        "model_type": BASE_MODEL_TYPE,
        "feature_group": BASE_FEATURE_GROUP,
        "feature_columns": list(FEATURE_GROUPS[BASE_FEATURE_GROUP]),
        "hyperparameters": {"C": BASE_LOGISTIC_REGRESSION_C},
        "persistence_samples": 3,
        "source_feature_schema_version": dataset.manifest.get("feature_schema_version"),
        "source_dataset_id": dataset.manifest["source_dataset"]["dataset_id"],
    }
    (artifacts_dir / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str)
    )


@dataclass(frozen=True)
class TinyFrozenArtifacts:
    training_features_dir: Path
    training_dataset_dir: Path
    models_dir: Path
    alert_policy_dir: Path


@pytest.fixture(scope="module")
def tiny_frozen_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> TinyFrozenArtifacts:
    root = tmp_path_factory.mktemp("ood-training")
    features_dir, dataset_dir = _build_features(
        root,
        dataset_id="ood-training-fixture",
        fault_start=150.0,
        seeds=tuple(range(301, 301 + 4 * _RUNS_PER_SCENARIO)),
        operating_condition_ranges=OperatingConditionRanges(),
        sensor_noise=(),
    )
    models_dir = root / "models"
    alert_policy_dir = root / "alert-policy"
    _write_frozen_model_artifact(features_dir, dataset_dir, models_dir)
    generate_alert_policy(
        features_dir,
        alert_policy_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )
    return TinyFrozenArtifacts(
        training_features_dir=features_dir,
        training_dataset_dir=dataset_dir,
        models_dir=models_dir,
        alert_policy_dir=alert_policy_dir,
    )


@pytest.fixture(scope="module")
def tiny_ood_features_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    """A second tiny real dataset shaped like `pem_faults_ood_v1.json`'s
    shifts at small scale: disjoint seeds, a shifted operating envelope, a
    later fault onset, and doubled sensor noise."""
    root = tmp_path_factory.mktemp("ood-shifted")
    return _build_features(
        root,
        dataset_id="ood-shifted-fixture",
        fault_start=200.0,
        seeds=tuple(range(90001, 90001 + 4 * _RUNS_PER_SCENARIO)),
        operating_condition_ranges=OperatingConditionRanges(
            load_baseline_percent=(75.0, 80.0),
            load_amplitude_percent=(5.0, 8.0),
            initial_stack_temperature_offset_celsius=(5.0, 8.0),
        ),
        sensor_noise=(
            SensorNoiseConfig(
                measurement_name="stack_temperature", standard_deviation=0.6
            ),
            SensorNoiseConfig(measurement_name="fuel_flow", standard_deviation=1.0),
        ),
    )
