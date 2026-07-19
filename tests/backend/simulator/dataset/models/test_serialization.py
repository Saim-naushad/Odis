"""Serialized pipeline round-trips and reproduces identical predictions
(PR168 spec section 13, "Serialization" test group)."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from backend.simulator.dataset.models.data import load_experiment_dataset
from backend.simulator.dataset.models.experiment import run_experiment


def test_selected_pipeline_round_trips_through_joblib(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    result = run_experiment(dataset)

    test_mask = dataset.split_mask("test")
    x_test = dataset.X_group(result.ablation.selected.feature_group, test_mask)
    original_predictions = result.pipeline.predict(x_test)

    artifact_path = tmp_path / "selected_pipeline.joblib"
    joblib.dump(result.pipeline, artifact_path)
    reloaded = joblib.load(artifact_path)

    reloaded_predictions = reloaded.predict(x_test)
    assert np.array_equal(original_predictions, reloaded_predictions)

    # Probability-free sanity: the reloaded pipeline is a fully independent
    # object graph, not a reference to the original.
    assert reloaded is not result.pipeline
