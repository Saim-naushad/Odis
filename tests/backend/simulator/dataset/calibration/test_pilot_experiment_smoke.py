"""Full pilot-style calibration experiment, end to end (PR169 spec
section 11, "Pilot experiment").

Checks output *structure* and broad sanity bounds — not exact metric
values, which can shift across supported scikit-learn versions."""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.calibration.config import (
    CONFIDENCE_THRESHOLD_GRID,
    PERSISTENCE_GRID,
)
from backend.simulator.dataset.calibration.generate import (
    CalibrationOutputExistsError,
    generate_calibration,
)


def test_full_pilot_calibration_experiment_produces_every_required_artifact(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "calibration-output"

    result = generate_calibration(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    assert result.selected_confidence_threshold in CONFIDENCE_THRESHOLD_GRID
    assert result.selected_persistence_samples in PERSISTENCE_GRID
    assert 0.0 <= result.test_balanced_accuracy_covered <= 1.0
    assert 0.0 <= result.test_coverage <= 1.0
    assert result.test_false_alarms_per_healthy_hour >= 0.0

    assert (output_dir / "calibration_summary.json").is_file()
    assert (output_dir / "policy_search.json").is_file()
    assert (output_dir / "uncertainty_report.md").is_file()
    assert (output_dir / "artifacts" / "calibrated_pipeline.joblib").is_file()
    assert (output_dir / "artifacts" / "decision_policy.json").is_file()
    assert (output_dir / "artifacts" / "model_card.md").is_file()

    summary = json.loads((output_dir / "calibration_summary.json").read_text())
    assert "calibration_metrics" in summary
    assert "pr168_comparison" in summary
    assert summary["pr168_comparison"]["pr168_baseline"]["persistence_samples"] == 3

    policy_search = json.loads((output_dir / "policy_search.json").read_text())
    expected_candidate_count = len(CONFIDENCE_THRESHOLD_GRID) * len(PERSISTENCE_GRID)
    assert len(policy_search["candidates"]) == expected_candidate_count

    decision_policy = json.loads(
        (output_dir / "artifacts" / "decision_policy.json").read_text()
    )
    assert (
        decision_policy["confidence_threshold"] == result.selected_confidence_threshold
    )
    assert decision_policy["persistence_samples"] == result.selected_persistence_samples
    assert len(decision_policy["class_order"]) == 4

    model_card = (output_dir / "artifacts" / "model_card.md").read_text()
    assert "not production-ready" in model_card
    assert "cooling_degradation" in model_card


def test_overwrite_flag_required_to_replace_existing_output(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "calibration-output"
    generate_calibration(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    try:
        generate_calibration(
            features_dir,
            output_dir,
            dataset_directory=dataset_dir,
            generation_command="test",
        )
        raised = False
    except CalibrationOutputExistsError:
        raised = True
    assert raised

    generate_calibration(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        overwrite=True,
        generation_command="test",
    )
    assert (output_dir / "calibration_summary.json").is_file()
