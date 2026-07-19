"""Identical input + seed produce identical selection and metrics (PR168
spec section 13, "Reproducibility" test group)."""

from __future__ import annotations

from pathlib import Path

from backend.simulator.dataset.models.data import load_experiment_dataset
from backend.simulator.dataset.models.experiment import run_experiment


def test_run_experiment_is_deterministic(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)

    result_a = run_experiment(dataset)
    result_b = run_experiment(dataset)

    selected_a = result_a.ablation.selected.to_json_dict()
    selected_b = result_b.ablation.selected.to_json_dict()
    assert selected_a == selected_b
    assert result_a.persistence_policy.selected_persistence_samples == (
        result_b.persistence_policy.selected_persistence_samples
    )
    assert (
        result_a.validation_metrics.balanced_accuracy
        == result_b.validation_metrics.balanced_accuracy
    )
    assert (
        result_a.test_metrics.balanced_accuracy
        == result_b.test_metrics.balanced_accuracy
    )
    assert (
        result_a.test_metrics.confusion_matrix == result_b.test_metrics.confusion_matrix
    )
    assert [t.to_json_dict() for t in result_a.ablation.all_trials] == [
        t.to_json_dict() for t in result_b.ablation.all_trials
    ]
