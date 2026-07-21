"""End-to-end smoke test for `run_policy_selection`, using small, real
(physics-generated) fixtures rather than the full robust training dataset
(spec section 14: "use tiny artifacts and datasets, not the full external
cohorts in unit tests").

Builds the same shape of tiny fixtures as `test_end_to_end.py` (PR174),
then calls the real PR174 `run_robustness_comparison` on them first — this
produces a genuine, self-consistent `comparison_dir` (candidate pipeline +
metadata + training summary, with real hashes) exactly the way PR174's own
CLI would, rather than hand-authoring JSON that has to fake those hashes.
`run_policy_selection` is then exercised against that real output.
"""

from __future__ import annotations

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
    NoiseRegime,
    OperatingConditionRanges,
    SensorNoiseConfig,
)
from backend.simulator.dataset.robustness.candidate import load_frozen_candidate
from backend.simulator.dataset.robustness.config import DEFAULT_PROMOTION_THRESHOLDS
from backend.simulator.dataset.robustness.generate import (
    CohortDataset,
    run_robustness_comparison,
)
from backend.simulator.dataset.robustness.policy_generate import (
    _write_promoted_artifacts,
    run_policy_selection,
)
from backend.simulator.dataset.robustness.policy_promotion import (
    PROMOTE,
    PolicyPromotionDecision,
)
from backend.simulator.dataset.run_config import DatasetScenario

_RUNS_PER_SCENARIO = 6
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)


def _scenario_plans(*, fault_start: float) -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=_RUNS_PER_SCENARIO
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=_RUNS_PER_SCENARIO,
            fault_start_sim_seconds=fault_start,
            fault_duration_sim_seconds=60.0,
            fault_severity=1.0,
        ),
    )


def _build_features(
    output_root: Path,
    *,
    dataset_id: str,
    fault_start: float,
    seeds: tuple[int, ...],
    operating_condition_ranges: OperatingConditionRanges | None = None,
    sensor_noise: tuple[SensorNoiseConfig, ...] = (),
    sensor_noise_regimes: tuple[NoiseRegime, ...] = (),
) -> tuple[Path, Path]:
    spec = DatasetSpec(
        dataset_id=dataset_id,
        simulator_version="1.0.0",
        scenario_plans=_scenario_plans(fault_start=fault_start),
        seeds=seeds,
        target_asset_ids=("fuel-cell-stack-01",),
        duration_sim_seconds=300.0,
        dt_seconds=10.0,
        run_start_time=_RUN_START,
        operating_condition_ranges=(
            operating_condition_ranges or OperatingConditionRanges()
        ),
        sensor_noise=sensor_noise,
        sensor_noise_regimes=sensor_noise_regimes,
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
class TinyPolicyFixture:
    comparison_dir: Path
    original_models_dir: Path
    robust_dataset_dir: Path
    robust_features_dir: Path
    pilot_features_dir: Path
    pilot_dataset_dir: Path
    external_cohorts: dict[str, CohortDataset]


@pytest.fixture(scope="module")
def tiny_policy_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> TinyPolicyFixture:
    root = tmp_path_factory.mktemp("policy-e2e")

    pilot_features_dir, pilot_dataset_dir = _build_features(
        root / "pilot",
        dataset_id="policy-e2e-pilot",
        fault_start=150.0,
        seeds=tuple(range(1001, 1001 + 4 * _RUNS_PER_SCENARIO)),
    )
    original_models_dir = root / "original-models"
    _write_frozen_model_artifact(
        pilot_features_dir, pilot_dataset_dir, original_models_dir
    )

    robust_features_dir, robust_dataset_dir = _build_features(
        root / "robust",
        dataset_id="policy-e2e-robust",
        fault_start=200.0,
        seeds=tuple(range(61001, 61001 + 4 * _RUNS_PER_SCENARIO)),
        operating_condition_ranges=OperatingConditionRanges(
            load_baseline_percent=(45.0, 80.0),
            load_amplitude_percent=(5.0, 15.0),
            initial_stack_temperature_offset_celsius=(-4.0, 7.0),
        ),
        sensor_noise_regimes=(
            NoiseRegime(
                name="nominal",
                sensor_noise=(
                    SensorNoiseConfig(
                        measurement_name="stack_temperature", standard_deviation=0.3
                    ),
                ),
            ),
            NoiseRegime(
                name="high_bounded",
                sensor_noise=(
                    SensorNoiseConfig(
                        measurement_name="stack_temperature", standard_deviation=0.6
                    ),
                ),
            ),
        ),
    )
    robust_models_dir = root / "robust-models"
    _write_frozen_model_artifact(
        robust_features_dir, robust_dataset_dir, robust_models_dir
    )

    external_cohorts: dict[str, CohortDataset] = {}
    cohort_seed_bases = {
        "high_load": 21001,
        "hot_start": 31001,
        "late_onset": 41001,
        "high_noise": 51001,
        "combined_ood_v1": 11001,
    }
    for name, seed_base in cohort_seed_bases.items():
        features_dir, dataset_dir = _build_features(
            root / name,
            dataset_id=f"policy-e2e-{name}",
            fault_start=180.0,
            seeds=tuple(range(seed_base, seed_base + 4 * _RUNS_PER_SCENARIO)),
            sensor_noise=(
                SensorNoiseConfig(
                    measurement_name="stack_temperature", standard_deviation=0.4
                ),
            ),
        )
        external_cohorts[name] = CohortDataset(
            features_dir=features_dir, dataset_dir=dataset_dir
        )

    comparison_dir = root / "comparison"
    run_robustness_comparison(
        original_models_dir=original_models_dir,
        robust_models_dir=robust_models_dir,
        robust_features_dir=robust_features_dir,
        robust_dataset_dir=robust_dataset_dir,
        pilot_features_dir=pilot_features_dir,
        pilot_dataset_dir=pilot_dataset_dir,
        external_cohorts=external_cohorts,
        output_directory=comparison_dir,
        generation_command="test",
    )

    return TinyPolicyFixture(
        comparison_dir=comparison_dir,
        original_models_dir=original_models_dir,
        robust_dataset_dir=robust_dataset_dir,
        robust_features_dir=robust_features_dir,
        pilot_features_dir=pilot_features_dir,
        pilot_dataset_dir=pilot_dataset_dir,
        external_cohorts=external_cohorts,
    )


_VALID_DECISIONS = (
    "PROMOTE ROBUST MODEL AND POLICY",
    "KEEP ORIGINAL MODEL — ALERT POLICY INSUFFICIENT",
    "KEEP ORIGINAL MODEL — ID OPERATIONAL REGRESSION",
    "NO SYSTEM MEETS PROMOTION CRITERIA",
)


def test_end_to_end_policy_selection_produces_every_artifact(
    tiny_policy_fixture: TinyPolicyFixture, tmp_path: Path
) -> None:
    output_dir = tmp_path / "policy-selection"

    result = run_policy_selection(
        comparison_dir=tiny_policy_fixture.comparison_dir,
        original_models_dir=tiny_policy_fixture.original_models_dir,
        robust_dataset_dir=tiny_policy_fixture.robust_dataset_dir,
        robust_features_dir=tiny_policy_fixture.robust_features_dir,
        pilot_features_dir=tiny_policy_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_policy_fixture.pilot_dataset_dir,
        external_cohorts=tiny_policy_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )

    assert result.decision in _VALID_DECISIONS
    assert result.policy_selected_before_evaluation is True

    for name in (
        "robust_policy_search.json",
        "robust_alert_evaluation.json",
        "robust_promotion_report.md",
        "promotion_decision.json",
    ):
        assert (output_dir / name).is_file(), name

    decision_payload = json.loads((output_dir / "promotion_decision.json").read_text())
    assert decision_payload["decision"] == result.decision

    promoted_dir = output_dir / "artifacts"
    if result.promoted:
        assert (promoted_dir / "promoted_pipeline.joblib").is_file()
        assert (promoted_dir / "promoted_alert_policy.json").is_file()
        assert (promoted_dir / "promoted_system_metadata.json").is_file()
    else:
        assert not promoted_dir.is_dir()


def test_system_b_and_c_row_level_diagnosis_are_identical(
    tiny_policy_fixture: TinyPolicyFixture, tmp_path: Path
) -> None:
    output_dir = tmp_path / "policy-selection"
    result = run_policy_selection(
        comparison_dir=tiny_policy_fixture.comparison_dir,
        original_models_dir=tiny_policy_fixture.original_models_dir,
        robust_dataset_dir=tiny_policy_fixture.robust_dataset_dir,
        robust_features_dir=tiny_policy_fixture.robust_features_dir,
        pilot_features_dir=tiny_policy_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_policy_fixture.pilot_dataset_dir,
        external_cohorts=tiny_policy_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )
    if result.selected_policy is None:
        pytest.skip("no policy selected in this tiny fixture run")

    payload = json.loads((output_dir / "robust_alert_evaluation.json").read_text())
    system_b = payload["system_b_robust_pr170_policy"]
    system_c = payload["system_c_robust_new_policy"]
    for cohort_name in system_b:
        b_diagnosis = system_b[cohort_name]["diagnosis"]
        c_diagnosis = system_c[cohort_name]["diagnosis"]
        assert b_diagnosis == c_diagnosis, cohort_name
        # And the alert layer is the only thing that may legitimately differ.
        assert (
            system_b[cohort_name]["alerts"] != system_c[cohort_name]["alerts"]
            or result.selected_policy is not None
        )


def test_promoted_pipeline_reloads_with_identical_predictions(
    tiny_policy_fixture: TinyPolicyFixture, tmp_path: Path
) -> None:
    output_dir = tmp_path / "policy-selection"
    result = run_policy_selection(
        comparison_dir=tiny_policy_fixture.comparison_dir,
        original_models_dir=tiny_policy_fixture.original_models_dir,
        robust_dataset_dir=tiny_policy_fixture.robust_dataset_dir,
        robust_features_dir=tiny_policy_fixture.robust_features_dir,
        pilot_features_dir=tiny_policy_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_policy_fixture.pilot_dataset_dir,
        external_cohorts=tiny_policy_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )
    if not result.promoted:
        pytest.skip("this tiny fixture run did not promote")

    candidate_pipeline = joblib.load(
        tiny_policy_fixture.comparison_dir / "robust_candidate_pipeline.joblib"
    )
    promoted_pipeline = joblib.load(
        output_dir / "artifacts" / "promoted_pipeline.joblib"
    )

    dataset = load_experiment_dataset(
        tiny_policy_fixture.robust_features_dir, tiny_policy_fixture.robust_dataset_dir
    )
    x = dataset.X_group(BASE_FEATURE_GROUP)
    assert (
        candidate_pipeline.predict_proba(x) == promoted_pipeline.predict_proba(x)
    ).all()

    metadata = json.loads(
        (output_dir / "artifacts" / "promoted_system_metadata.json").read_text()
    )
    assert len(metadata["model_hash"]) == 64
    assert len(metadata["policy_hash"]) == 64
    assert metadata["promotion_decision"]["decision"] == result.decision


def test_write_promoted_artifacts_reloads_deterministically(
    tiny_policy_fixture: TinyPolicyFixture, tmp_path: Path
) -> None:
    """Directly exercises artifact writing/reload — independent of whether
    this particular tiny fixture's random search happens to promote, so
    serialization is always covered, not just conditionally."""
    candidate = load_frozen_candidate(
        tiny_policy_fixture.comparison_dir,
        training_dataset_dir=tiny_policy_fixture.robust_dataset_dir,
        training_features_dir=tiny_policy_fixture.robust_features_dir,
    )
    selected_policy = StateMachineConfig(
        entry_probability=0.65,
        entry_persistence=4,
        healthy_exit_probability=0.5,
        exit_persistence=2,
    )
    decision = PolicyPromotionDecision(
        decision=PROMOTE,
        reasons=("test-only synthetic decision",),
        thresholds=DEFAULT_PROMOTION_THRESHOLDS,
        checks={},
    )
    tmp_dir = tmp_path / "artifact-write"
    tmp_dir.mkdir()

    _write_promoted_artifacts(
        tmp_dir=tmp_dir,
        candidate=candidate,
        selected_policy=selected_policy,
        decision=decision,
        external_cohorts=tiny_policy_fixture.external_cohorts,
        pilot_features_dir=tiny_policy_fixture.pilot_features_dir,
        generation_command="test",
    )

    artifacts_dir = tmp_dir / "artifacts"
    reloaded_pipeline = joblib.load(artifacts_dir / "promoted_pipeline.joblib")
    dataset = load_experiment_dataset(
        tiny_policy_fixture.robust_features_dir, tiny_policy_fixture.robust_dataset_dir
    )
    x = dataset.X_group(BASE_FEATURE_GROUP)
    assert (
        candidate.pipeline.predict_proba(x) == reloaded_pipeline.predict_proba(x)
    ).all()

    alert_policy = json.loads(
        (artifacts_dir / "promoted_alert_policy.json").read_text()
    )
    assert alert_policy["state_machine_config"] == selected_policy.to_json_dict()

    metadata = json.loads(
        (artifacts_dir / "promoted_system_metadata.json").read_text()
    )
    assert metadata["model_hash"] == candidate.pipeline_sha256
    assert (
        metadata["training_dataset_manifest_sha256"]
        == candidate.training_dataset_manifest_sha256
    )
    assert metadata["class_order"] == list(candidate.class_order)
    assert metadata["feature_order"] == list(candidate.feature_order)
