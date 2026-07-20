"""Deterministic state sequences and policy JSON round-tripping (PR170
spec section 10, "Reproducibility and serialization" test group)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.simulator.dataset.alert_policy.experiment import (
    run_alert_policy_experiment,
)
from backend.simulator.dataset.alert_policy.report import build_alert_policy_artifact
from backend.simulator.dataset.alert_policy.state_machine import (
    StateMachineConfig,
    run_state_machine,
)
from backend.simulator.dataset.models.data import load_experiment_dataset

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")
_CONFIG = StateMachineConfig(
    entry_probability=0.5,
    entry_persistence=3,
    healthy_exit_probability=0.6,
    exit_persistence=2,
)


def test_state_sequence_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    proba = rng.dirichlet(np.ones(4), size=20)
    elapsed = [i * 10.0 for i in range(20)]

    result_a = run_state_machine(elapsed, proba, _CLASSES, _CONFIG)
    result_b = run_state_machine(elapsed, proba, _CLASSES, _CONFIG)

    assert result_a.row_states == result_b.row_states
    assert [e.to_json_dict() for e in result_a.events] == [
        e.to_json_dict() for e in result_b.events
    ]


def test_full_experiment_is_deterministic(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)

    result_a = run_alert_policy_experiment(dataset)
    result_b = run_alert_policy_experiment(dataset)

    assert result_a.selected_config == result_b.selected_config
    assert (
        result_a.test_multiclass_metrics.balanced_accuracy
        == result_b.test_multiclass_metrics.balanced_accuracy
    )
    assert [c.to_json_dict() for c in result_a.policy_search.candidates] == [
        c.to_json_dict() for c in result_b.policy_search.candidates
    ]


def test_decision_policy_json_round_trips(tiny_features_dir: tuple[Path, Path]) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    result = run_alert_policy_experiment(dataset)

    artifact = build_alert_policy_artifact(result)
    round_tripped = json.loads(json.dumps(artifact, default=str))

    assert round_tripped["class_order"] == list(result.class_order)
    if result.selected_config is not None:
        expected = result.selected_config.to_json_dict()
        assert round_tripped["state_machine_config"] == expected
    assert round_tripped["base_model_reference"]["model_type"] == "logistic_regression"


def test_reloaded_policy_produces_identical_events(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    """Reconstructing a `StateMachineConfig` from the round-tripped JSON
    and re-running the state machine gives byte-identical events to the
    original in-memory config."""
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    result = run_alert_policy_experiment(dataset)
    if result.selected_config is None:
        return  # nothing to reload if no policy was selected

    artifact = build_alert_policy_artifact(result)
    round_tripped = json.loads(json.dumps(artifact, default=str))
    reloaded_dict = round_tripped["state_machine_config"]
    reloaded_config = StateMachineConfig(
        entry_probability=reloaded_dict["entry_probability"],
        entry_persistence=reloaded_dict["entry_persistence"],
        healthy_exit_probability=reloaded_dict["healthy_exit_probability"],
        exit_persistence=reloaded_dict["exit_persistence"],
    )

    test_mask = dataset.split_mask("test")
    run_id = next(
        run_id
        for run_id, metadata in dataset.run_metadata.items()
        if metadata.split == "test" and metadata.fault_class is not None
    )
    metadata = dataset.run_metadata[run_id]
    indices = np.nonzero(test_mask)[0]
    positions = [
        p
        for p in range(len(indices))
        if dataset.run_ids[indices[p]] == run_id
        and dataset.asset_ids[indices[p]] == metadata.target_asset_id
    ]
    positions.sort(key=lambda p: dataset.elapsed_sim_seconds[indices[p]])
    elapsed = [float(dataset.elapsed_sim_seconds[indices[p]]) for p in positions]
    proba = result.test_proba[positions]

    original_config = result.selected_config
    original = run_state_machine(elapsed, proba, result.class_order, original_config)
    reloaded = run_state_machine(elapsed, proba, result.class_order, reloaded_config)

    assert original.row_states == reloaded.row_states
    assert [e.to_json_dict() for e in original.events] == [
        e.to_json_dict() for e in reloaded.events
    ]
