"""Shared fixtures for PR176 runtime-inference tests: a tiny, real
(physics-generated) dataset, its offline `features.parquet`, a frozen
baseline pipeline fit directly on it, and a packaged runtime bundle built
from all of that — mirrors `ood/conftest.py`'s `tiny_frozen_artifacts`
rationale (a real ablation search is not guaranteed to reproduce a
specific model_type/feature_group at this scale, so the baseline is fit
directly instead) extended one step further: PR176 additionally needs a
real `alert_policy.json` and a packaged `artifacts/models/...`-shaped
bundle to load through the actual runtime loader.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest

from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.features.config import FEATURE_SCHEMA_VERSION
from backend.simulator.dataset.features.generate import generate_features
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.manifest import resolve_git_commit
from backend.simulator.dataset.models.data import load_experiment_dataset
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.models.selected_baseline import BASE_FEATURE_GROUP
from backend.simulator.dataset.operating_conditions import OperatingConditionRanges
from backend.simulator.dataset.run_config import DatasetScenario
from backend.simulator.inference.bundle import BUNDLE_FILENAMES, _canonical_json_hash
from backend.simulator.inference.loader import (
    PromotedFaultSystem,
    load_promoted_fault_system,
)

_RUNS_PER_SCENARIO = 6
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)
_FAULT_START = 150.0
_FAULT_DURATION = 60.0
_TEST_ALERT_POLICY = StateMachineConfig(
    entry_probability=0.60,
    entry_persistence=3,
    healthy_exit_probability=0.50,
    exit_persistence=2,
)


def _scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=_RUNS_PER_SCENARIO
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=1.0,
        ),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TinyRuntimeFixture:
    dataset_dir: Path
    features_dir: Path
    bundle_dir: Path
    system: PromotedFaultSystem


@pytest.fixture(scope="module")
def tiny_runtime_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> TinyRuntimeFixture:
    root = tmp_path_factory.mktemp("runtime-inference")

    spec = DatasetSpec(
        dataset_id="runtime-inference-fixture",
        simulator_version="1.0.0",
        scenario_plans=_scenario_plans(),
        seeds=tuple(range(701, 701 + 4 * _RUNS_PER_SCENARIO)),
        target_asset_ids=("fuel-cell-stack-01",),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        run_start_time=_RUN_START,
        operating_condition_ranges=OperatingConditionRanges(),
        sensor_noise=(),
        split_proportions=SplitProportions(train=0.5, validation=0.25, test=0.25),
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
    pipeline.fit(dataset.X_group(BASE_FEATURE_GROUP, train_mask), dataset.y[train_mask])
    class_order = tuple(pipeline.named_steps["classifier"].classes_)

    bundle_dir = root / "bundle"
    bundle_dir.mkdir(parents=True)

    pipeline_path = bundle_dir / "pipeline.joblib"
    joblib.dump(pipeline, pipeline_path)
    pipeline_hash = _sha256_file(pipeline_path)

    alert_policy_payload = {
        "class_order": list(class_order),
        "state_machine_config": _TEST_ALERT_POLICY.to_json_dict(),
    }
    alert_policy_path = bundle_dir / "alert_policy.json"
    alert_policy_path.write_text(json.dumps(alert_policy_payload, indent=2))
    policy_hash = _sha256_file(alert_policy_path)

    git_commit, _status = resolve_git_commit()
    metadata_payload = {
        "system_version": "test-fixture-v1",
        "packaged_at": datetime.now(UTC).isoformat(),
        "source_directory": str(root),
        "model_hash": pipeline_hash,
        "policy_hash": policy_hash,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "safety_policy_version": FEATURE_SCHEMA_VERSION,
        "feature_order": list(FEATURE_GROUPS[BASE_FEATURE_GROUP]),
        "class_order": list(class_order),
        "model_type": "logistic_regression",
        "feature_group": BASE_FEATURE_GROUP,
        "hyperparameters": {"C": 0.1},
        "training_dataset_id": "runtime-inference-fixture",
        "training_dataset_manifest_sha256": "0" * 64,
        "training_feature_manifest_sha256": "0" * 64,
        "git_commit": git_commit,
        "promotion_decision": "TEST FIXTURE",
    }
    metadata_hash = _canonical_json_hash(metadata_payload)
    (bundle_dir / "system_metadata.json").write_text(
        json.dumps({**metadata_payload, "metadata_hash": metadata_hash})
    )
    assert {p.name for p in bundle_dir.iterdir()} == set(BUNDLE_FILENAMES)

    system = load_promoted_fault_system(bundle_dir)

    return TinyRuntimeFixture(
        dataset_dir=dataset_result.output_directory,
        features_dir=features_dir,
        bundle_dir=bundle_dir,
        system=system,
    )
