"""Full pilot-style experiment run, end to end (PR168 spec section 13,
"Pilot experiment").

Deliberately checks output *structure* and broad sanity bounds, not exact
metric values — those can shift across supported scikit-learn versions
(spec section 13: "Do not make tests depend on exact real-pilot metric
values except broad sanity bounds")."""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.models.config import FEATURE_GROUP_NAMES, PRIMARY_CLASSES
from backend.simulator.dataset.models.generate import (
    ModelOutputExistsError,
    generate_models,
)
from backend.simulator.dataset.models.search import (
    HISTOGRAM_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
)


def test_full_pilot_experiment_produces_every_required_artifact(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "models-output"

    result = generate_models(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    valid_model_types = (LOGISTIC_REGRESSION, HISTOGRAM_GRADIENT_BOOSTING)
    assert result.selected_model_type in valid_model_types
    assert 0.0 <= result.validation_balanced_accuracy <= 1.0
    assert 0.0 <= result.test_balanced_accuracy <= 1.0

    # Required output artifacts (spec section 11).
    assert (output_dir / "experiment_summary.json").is_file()
    assert (output_dir / "evaluation_report.md").is_file()
    assert (output_dir / "metrics" / "validation_metrics.json").is_file()
    assert (output_dir / "metrics" / "test_metrics.json").is_file()
    assert (output_dir / "artifacts" / "selected_pipeline.joblib").is_file()
    assert (output_dir / "artifacts" / "model_metadata.json").is_file()

    summary = json.loads((output_dir / "experiment_summary.json").read_text())
    assert summary["selected_model"]["feature_group"] in FEATURE_GROUP_NAMES
    # Every (feature group x model) combination must have been tried —
    # spec section 2: "Do not report only the best configuration."
    trials = summary["ablation"]["all_trials"]
    tried_combinations = {(t["feature_group"], t["model_type"]) for t in trials}
    expected_combinations = {
        (group, model)
        for group in FEATURE_GROUP_NAMES
        for model in (LOGISTIC_REGRESSION, HISTOGRAM_GRADIENT_BOOSTING)
    }
    assert expected_combinations <= tried_combinations

    test_metrics_path = output_dir / "metrics" / "test_metrics.json"
    test_metrics = json.loads(test_metrics_path.read_text())
    assert set(test_metrics["multiclass"]["class_order"]) == set(PRIMARY_CLASSES)
    assert "detection" in test_metrics["operational"]
    assert "runtime" in test_metrics

    metadata_path = output_dir / "artifacts" / "model_metadata.json"
    model_metadata = json.loads(metadata_path.read_text())
    assert model_metadata["model_type"] == result.selected_model_type
    assert len(model_metadata["feature_columns"]) > 0


def test_overwrite_flag_required_to_replace_existing_output(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, dataset_dir = tiny_features_dir
    output_dir = tmp_path / "models-output"
    generate_models(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        generation_command="test",
    )

    try:
        generate_models(
            features_dir,
            output_dir,
            dataset_directory=dataset_dir,
            generation_command="test",
        )
        raised = False
    except ModelOutputExistsError:
        raised = True
    assert raised

    # overwrite=True must succeed and replace the directory
    generate_models(
        features_dir,
        output_dir,
        dataset_directory=dataset_dir,
        overwrite=True,
        generation_command="test",
    )
    assert (output_dir / "experiment_summary.json").is_file()
