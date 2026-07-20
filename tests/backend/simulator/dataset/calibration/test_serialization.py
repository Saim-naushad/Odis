"""Serialized calibrated pipeline and decision-policy round-tripping
(PR169 spec section 11, "Serialization" test group)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from backend.simulator.dataset.calibration.experiment import run_calibration_experiment
from backend.simulator.dataset.calibration.report import build_decision_policy
from backend.simulator.dataset.models.data import load_experiment_dataset


def test_calibrated_pipeline_round_trips_through_joblib(
    tiny_features_dir: tuple[Path, Path], tmp_path: Path
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    result = run_calibration_experiment(dataset)

    test_mask = dataset.split_mask("test")
    x_test = dataset.X_group("D", test_mask)
    original_proba = result.calibrated_model.predict_proba(x_test)
    original_diagnosis = result.calibrated_model.calibrated_pipeline.predict(x_test)

    artifact_path = tmp_path / "calibrated_pipeline.joblib"
    joblib.dump(result.calibrated_model.calibrated_pipeline, artifact_path)
    reloaded = joblib.load(artifact_path)

    reloaded_proba = reloaded.predict_proba(x_test)
    reloaded_diagnosis = reloaded.predict(x_test)

    np.testing.assert_allclose(original_proba, reloaded_proba)
    assert np.array_equal(original_diagnosis, reloaded_diagnosis)
    assert tuple(reloaded.classes_) == result.calibrated_model.class_order
    assert reloaded is not result.calibrated_model.calibrated_pipeline


def test_decision_policy_json_round_trips(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    result = run_calibration_experiment(dataset)

    decision_policy = build_decision_policy(result)
    round_tripped = json.loads(json.dumps(decision_policy, default=str))

    assert round_tripped["class_order"] == list(result.calibrated_model.class_order)
    assert round_tripped["confidence_threshold"] == result.selected_confidence_threshold
    assert round_tripped["persistence_samples"] == result.selected_persistence_samples
    assert round_tripped["uncertain_breaks_persistence_sequence"] is True
