"""End-to-end smoke test for `run_robustness_comparison`, using small,
real (physics-generated) fixtures rather than the full 192-run robust
training dataset (spec section 14: "use smaller fixtures ... in normal
unit tests").

Builds two tiny datasets — an "original" one (narrow ranges, no noise,
mirroring the pilot) and a "robust" one (broader ranges, a noise-regime
set, disjoint seeds, mirroring `pem_faults_robust_training_v1.json` at
small scale) — fits the frozen baseline pipeline directly on each (see
`ood/conftest.py`'s `tiny_frozen_artifacts` for why: at this scale, a real
ablation search is not guaranteed to reproduce a specific model_type/
feature_group, which would make these tests fixture-dependent rather than
a real test of the robustness package), and a handful of tiny "external
cohort" datasets distinct from both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest

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
from backend.simulator.dataset.robustness.config import EXTERNAL_COHORT_NAMES
from backend.simulator.dataset.robustness.generate import (
    CohortDataset,
    run_robustness_comparison,
)
from backend.simulator.dataset.run_config import DatasetScenario

_RUNS_PER_SCENARIO = 4
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
    """Fit and serialize exactly the frozen baseline (logistic regression,
    feature group D, `C=0.01`) directly on `features_dir`'s train split —
    mirrors `ood/conftest.py`'s `_write_frozen_model_artifact`."""
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
class TinyRobustnessFixture:
    original_models_dir: Path
    robust_models_dir: Path
    robust_features_dir: Path
    robust_dataset_dir: Path
    pilot_features_dir: Path
    pilot_dataset_dir: Path
    external_cohorts: dict[str, CohortDataset]


@pytest.fixture(scope="module")
def tiny_robustness_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> TinyRobustnessFixture:
    root = tmp_path_factory.mktemp("robustness")

    pilot_features_dir, pilot_dataset_dir = _build_features(
        root / "pilot",
        dataset_id="robustness-pilot-fixture",
        fault_start=150.0,
        seeds=tuple(range(1001, 1001 + 4 * _RUNS_PER_SCENARIO)),
    )
    original_models_dir = root / "original-models"
    _write_frozen_model_artifact(
        pilot_features_dir, pilot_dataset_dir, original_models_dir
    )

    robust_features_dir, robust_dataset_dir = _build_features(
        root / "robust",
        dataset_id="robustness-robust-fixture",
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
            dataset_id=f"robustness-{name}-fixture",
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

    return TinyRobustnessFixture(
        original_models_dir=original_models_dir,
        robust_models_dir=robust_models_dir,
        robust_features_dir=robust_features_dir,
        robust_dataset_dir=robust_dataset_dir,
        pilot_features_dir=pilot_features_dir,
        pilot_dataset_dir=pilot_dataset_dir,
        external_cohorts=external_cohorts,
    )


def test_end_to_end_comparison_produces_every_artifact(
    tiny_robustness_fixture: TinyRobustnessFixture, tmp_path: Path
) -> None:
    output_dir = tmp_path / "comparison"

    result = run_robustness_comparison(
        original_models_dir=tiny_robustness_fixture.original_models_dir,
        robust_models_dir=tiny_robustness_fixture.robust_models_dir,
        robust_features_dir=tiny_robustness_fixture.robust_features_dir,
        robust_dataset_dir=tiny_robustness_fixture.robust_dataset_dir,
        pilot_features_dir=tiny_robustness_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_robustness_fixture.pilot_dataset_dir,
        external_cohorts=tiny_robustness_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )

    assert result.decision in (
        "PROMOTE ROBUST MODEL",
        "KEEP ORIGINAL MODEL — ROBUSTNESS GAINS INSUFFICIENT",
        "KEEP ORIGINAL MODEL — ID REGRESSION TOO LARGE",
        "NO MODEL READY — FURTHER FEATURE/DATA REVISION REQUIRED",
    )

    for name in (
        "robust_candidate_pipeline.joblib",
        "robust_candidate_metadata.json",
        "robust_training_summary.json",
        "robust_evaluation_report.md",
        "promotion_decision.json",
        "cohort_comparisons.json",
    ):
        assert (output_dir / name).is_file(), name

    comparisons = json.loads((output_dir / "cohort_comparisons.json").read_text())
    assert set(comparisons) == set(EXTERNAL_COHORT_NAMES)

    decision = json.loads((output_dir / "promotion_decision.json").read_text())
    assert decision["decision"] == result.decision


def test_reloaded_candidate_pipeline_predicts_identically(
    tiny_robustness_fixture: TinyRobustnessFixture, tmp_path: Path
) -> None:
    """The copied `robust_candidate_pipeline.joblib` must be the exact same
    fitted pipeline as the robust `models` artifact — proof this module
    never refits anything, only copies and scores an already-frozen model."""
    output_dir = tmp_path / "comparison"
    run_robustness_comparison(
        original_models_dir=tiny_robustness_fixture.original_models_dir,
        robust_models_dir=tiny_robustness_fixture.robust_models_dir,
        robust_features_dir=tiny_robustness_fixture.robust_features_dir,
        robust_dataset_dir=tiny_robustness_fixture.robust_dataset_dir,
        pilot_features_dir=tiny_robustness_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_robustness_fixture.pilot_dataset_dir,
        external_cohorts=tiny_robustness_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )

    robust_models_dir = tiny_robustness_fixture.robust_models_dir
    original_pipeline = joblib.load(
        robust_models_dir / "artifacts" / "selected_pipeline.joblib"
    )
    reloaded_pipeline = joblib.load(output_dir / "robust_candidate_pipeline.joblib")

    dataset = load_experiment_dataset(
        tiny_robustness_fixture.robust_features_dir,
        tiny_robustness_fixture.robust_dataset_dir,
    )
    x = dataset.X_group(BASE_FEATURE_GROUP)
    assert (
        original_pipeline.predict_proba(x) == reloaded_pipeline.predict_proba(x)
    ).all()


def test_every_cohort_is_scored_by_the_same_frozen_candidate(
    tiny_robustness_fixture: TinyRobustnessFixture, tmp_path: Path
) -> None:
    """Feature schema/order compatibility across every cohort: if any
    cohort's feature columns didn't match the frozen pipeline's expected
    order, `evaluate_model_on_cohort` (via `models.data.load_experiment_
    dataset`) would already have raised before this comparison could
    complete — so a successful run is itself the compatibility proof."""
    output_dir = tmp_path / "comparison"
    result = run_robustness_comparison(
        original_models_dir=tiny_robustness_fixture.original_models_dir,
        robust_models_dir=tiny_robustness_fixture.robust_models_dir,
        robust_features_dir=tiny_robustness_fixture.robust_features_dir,
        robust_dataset_dir=tiny_robustness_fixture.robust_dataset_dir,
        pilot_features_dir=tiny_robustness_fixture.pilot_features_dir,
        pilot_dataset_dir=tiny_robustness_fixture.pilot_dataset_dir,
        external_cohorts=tiny_robustness_fixture.external_cohorts,
        output_directory=output_dir,
        generation_command="test",
    )
    assert result.output_directory == output_dir
