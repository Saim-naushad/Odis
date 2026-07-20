"""End-to-end OOD evaluation smoke test on tiny generated datasets (spec
section 14, "End-to-end smoke") plus reproducibility (spec section 14,
"Reproducibility").

Uses tiny, deterministic artifacts throughout — never asserts exact
full-pilot OOD metrics, only structural/consistency properties.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.ood.artifacts import load_frozen_artifacts
from backend.simulator.dataset.ood.data_loading import load_ood_experiment_dataset
from backend.simulator.dataset.ood.diagnosis_metrics import predict
from backend.simulator.dataset.ood.error_analysis import select_representative_cases
from backend.simulator.dataset.ood.generate import run_ood_evaluation
from backend.simulator.dataset.ood.verdict import Verdict
from tests.backend.simulator.dataset.ood.conftest import TinyFrozenArtifacts


def test_full_evaluation_produces_every_required_artifact(
    tiny_frozen_artifacts: TinyFrozenArtifacts,
    tiny_ood_features_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ood_features_dir, ood_dataset_dir = tiny_ood_features_dir
    output_dir = tmp_path / "ood-evaluation"

    result = run_ood_evaluation(
        training_features_dir=tiny_frozen_artifacts.training_features_dir,
        training_dataset_dir=tiny_frozen_artifacts.training_dataset_dir,
        ood_features_dir=ood_features_dir,
        ood_dataset_dir=ood_dataset_dir,
        models_dir=tiny_frozen_artifacts.models_dir,
        alert_policy_dir=tiny_frozen_artifacts.alert_policy_dir,
        output_directory=output_dir,
        generation_command="test",
    )

    assert (output_dir / "ood_evaluation_summary.json").is_file()
    assert (output_dir / "ood_evaluation_report.md").is_file()
    assert (output_dir / "feature_shift.json").is_file()
    assert (output_dir / "error_cases.json").is_file()

    valid_verdicts: tuple[Verdict, ...] = (
        "GENERALIZES ACCEPTABLY TO OOD V1",
        "GENERALIZES WITH MATERIAL DEGRADATION",
        "DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED",
    )
    assert result.verdict in valid_verdicts
    assert 0.0 <= result.ood_balanced_accuracy <= 1.0
    assert result.ood_false_alert_events_per_healthy_hour >= 0.0

    summary = json.loads((output_dir / "ood_evaluation_summary.json").read_text())
    assert summary["verdict"]["verdict"] == result.verdict
    assert len(summary["frozen_artifacts"]["pipeline_sha256"]) == 64
    assert len(summary["frozen_artifacts"]["alert_policy_sha256"]) == 64

    # All OOD rows accounted for: scored rows + dropped-unscoreable rows
    # equal the feature manifest's total row count.
    ood_unscoreable = summary["ood_cohort"]["unscoreable_rows"]
    scored_rows = sum(
        entry["support"]
        for entry in summary["ood_cohort"]["diagnosis"]["multiclass_metrics"][
            "per_class"
        ].values()
    )
    assert scored_rows + ood_unscoreable["unscoreable_row_count"] == (
        ood_unscoreable["total_rows"]
    )

    # Severity/stage breakdowns present for every fault class.
    for cls in FAULT_CLASSES:
        assert cls in summary["ood_cohort"]["diagnosis"]["severity_band_recall"]
        assert cls in summary["ood_cohort"]["diagnosis"]["ramp_stage_recall"]


def test_repeated_evaluation_is_semantically_identical(
    tiny_frozen_artifacts: TinyFrozenArtifacts,
    tiny_ood_features_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ood_features_dir, ood_dataset_dir = tiny_ood_features_dir

    def _run(output_dir: Path) -> dict[str, object]:
        run_ood_evaluation(
            training_features_dir=tiny_frozen_artifacts.training_features_dir,
            training_dataset_dir=tiny_frozen_artifacts.training_dataset_dir,
            ood_features_dir=ood_features_dir,
            ood_dataset_dir=ood_dataset_dir,
            models_dir=tiny_frozen_artifacts.models_dir,
            alert_policy_dir=tiny_frozen_artifacts.alert_policy_dir,
            output_directory=output_dir,
            generation_command="test",
        )
        summary: dict[str, object] = json.loads(
            (output_dir / "ood_evaluation_summary.json").read_text()
        )
        summary.pop("generation_command")
        return summary

    first = _run(tmp_path / "run1")
    second = _run(tmp_path / "run2")
    assert first == second

    first_error_cases = json.loads(
        (tmp_path / "run1" / "error_cases.json").read_text()
    )
    second_error_cases = json.loads(
        (tmp_path / "run2" / "error_cases.json").read_text()
    )
    assert first_error_cases == second_error_cases


def test_alert_policy_config_is_not_mutated_by_evaluation(
    tiny_frozen_artifacts: TinyFrozenArtifacts,
    tiny_ood_features_dir: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ood_features_dir, ood_dataset_dir = tiny_ood_features_dir
    artifacts = load_frozen_artifacts(
        tiny_frozen_artifacts.models_dir, tiny_frozen_artifacts.alert_policy_dir
    )
    config_before = artifacts.state_machine_config

    run_ood_evaluation(
        training_features_dir=tiny_frozen_artifacts.training_features_dir,
        training_dataset_dir=tiny_frozen_artifacts.training_dataset_dir,
        ood_features_dir=ood_features_dir,
        ood_dataset_dir=ood_dataset_dir,
        models_dir=tiny_frozen_artifacts.models_dir,
        alert_policy_dir=tiny_frozen_artifacts.alert_policy_dir,
        output_directory=tmp_path / "ood-evaluation",
        generation_command="test",
    )

    artifacts_after = load_frozen_artifacts(
        tiny_frozen_artifacts.models_dir, tiny_frozen_artifacts.alert_policy_dir
    )
    assert artifacts_after.state_machine_config == config_before
    assert artifacts_after.pipeline_sha256 == artifacts.pipeline_sha256


def test_representative_case_selection_is_deterministic(
    tiny_frozen_artifacts: TinyFrozenArtifacts,
    tiny_ood_features_dir: tuple[Path, Path],
) -> None:
    ood_features_dir, ood_dataset_dir = tiny_ood_features_dir
    artifacts = load_frozen_artifacts(
        tiny_frozen_artifacts.models_dir, tiny_frozen_artifacts.alert_policy_dir
    )
    dataset, _ = load_ood_experiment_dataset(ood_features_dir, ood_dataset_dir)
    predictions = predict(dataset, artifacts.pipeline, artifacts.feature_group)

    from backend.simulator.dataset.ood.alert_metrics import evaluate_alert_policy

    alerts = evaluate_alert_policy(
        dataset,
        predictions.proba,
        artifacts.class_order,
        artifacts.state_machine_config,
    )

    first = select_representative_cases(
        dataset, predictions, alerts, artifacts.state_machine_config
    )
    second = select_representative_cases(
        dataset, predictions, alerts, artifacts.state_machine_config
    )
    assert [c.to_json_dict() for c in first] == [c.to_json_dict() for c in second]
