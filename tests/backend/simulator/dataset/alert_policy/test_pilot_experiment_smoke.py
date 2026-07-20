"""Full pilot-style alert-policy experiment, end to end (PR170 spec
section 10, "Pilot experiment").

Checks output *structure* and broad sanity bounds — not exact metric
values, which can shift across supported scikit-learn versions."""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.alert_policy.generate import (
    AlertPolicyOutputExistsError,
    generate_alert_policy,
)


def test_full_pilot_alert_policy_experiment_produces_every_required_artifact(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "alert-policy-output"

    result = generate_alert_policy(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    assert (output_dir / "alert_policy_search.json").is_file()
    assert (output_dir / "alert_evaluation_report.md").is_file()
    assert (output_dir / "artifacts" / "alert_policy.json").is_file()
    # No joblib artifact is expected: alert_policy.json references PR168's
    # model instead of duplicating it (spec section 9).
    assert not (output_dir / "artifacts" / "selected_pipeline.joblib").exists()
    assert not (output_dir / "artifacts" / "calibrated_pipeline.joblib").exists()

    search = json.loads((output_dir / "alert_policy_search.json").read_text())
    assert "policy_search" in search
    assert "validation_baseline" in search
    total_candidates = len(search["policy_search"]["candidates"])
    assert total_candidates == 72

    artifact = json.loads((output_dir / "artifacts" / "alert_policy.json").read_text())
    assert artifact["base_model_reference"]["model_type"] == "logistic_regression"
    assert artifact["base_model_reference"]["feature_group"] == "D"
    assert len(artifact["class_order"]) == 4
    assert "uncalibrated_notice" in artifact

    report = (output_dir / "alert_evaluation_report.md").read_text()
    assert "UNCALIBRATED" in report
    assert "PR168" in report and "PR169" in report

    if result.selected_entry_probability is not None:
        assert 0.0 < result.selected_entry_probability <= 1.0
        assert result.selected_entry_persistence is not None
        assert result.test_false_alert_events_per_healthy_hour is not None
        assert result.test_false_alert_events_per_healthy_hour >= 0.0


def test_overwrite_flag_required_to_replace_existing_output(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "alert-policy-output"
    generate_alert_policy(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    try:
        generate_alert_policy(
            features_dir,
            output_dir,
            dataset_directory=dataset_dir,
            generation_command="test",
        )
        raised = False
    except AlertPolicyOutputExistsError:
        raised = True
    assert raised

    generate_alert_policy(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        overwrite=True,
        generation_command="test",
    )
    assert (output_dir / "alert_policy_search.json").is_file()
