"""Top-level experiment orchestration (PR168 spec sections 2, 6, 8, 9, 11).

Pure computation over an already-loaded `ExperimentDataset` — no
filesystem writes here (those belong to `generate.py`, mirroring
`features/builder.py` vs. `features/generate.py`'s split). Test-split rows
are touched exactly once, after every model/feature-set/hyperparameter/
persistence-policy decision has already been made from validation alone.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.models.bootstrap import bootstrap_balanced_accuracy_ci
from backend.simulator.dataset.models.config import (
    FAULT_CLASSES,
    FEATURE_GROUP_NAMES,
    HEALTHY_LABEL,
    PERSISTENCE_CANDIDATES,
)
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.detection import (
    DetectionSummary,
    evaluate_detection,
)
from backend.simulator.dataset.models.metrics import (
    MulticlassMetrics,
    compute_multiclass_metrics,
)
from backend.simulator.dataset.models.reference_baseline import (
    ThresholdRule,
    evaluate_reference_rule,
    select_reference_threshold_rule,
)
from backend.simulator.dataset.models.runtime_metrics import (
    measure_per_row_prediction_latency_ms,
)
from backend.simulator.dataset.models.search import (
    HISTOGRAM_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
    SearchTrial,
    best_trial,
    build_pipeline_for_trial,
    fit_trial_pipeline,
    search_histogram_gb,
    search_logistic_regression,
)
from backend.simulator.dataset.models.severity import (
    GroupRecall,
    band_for,
    ramp_group_labels,
    recall_by_group,
)


def _severity_band_row_labels(dataset: ExperimentDataset) -> np.ndarray:
    """Each row's fault class's configured-maximum severity band, `None`
    for healthy rows or runs with no configured severity."""
    labels = np.full(len(dataset.run_ids), None, dtype=object)
    for i, run_id in enumerate(dataset.run_ids):
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or metadata.fault_class is None:
            continue
        labels[i] = band_for(metadata.configured_severity)
    return labels


def _ramp_row_labels(dataset: ExperimentDataset) -> np.ndarray:
    fault_duration_by_run = {
        run_id: metadata.fault_duration_sim_seconds
        for run_id, metadata in dataset.run_metadata.items()
    }
    return ramp_group_labels(
        dataset.seconds_since_fault_start, fault_duration_by_run, dataset.run_ids
    )


@dataclass(frozen=True)
class AblationResult:
    all_trials: list[SearchTrial]
    best_per_group_and_model: dict[tuple[str, str], SearchTrial]
    selected: SearchTrial

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "all_trials": [t.to_json_dict() for t in self.all_trials],
            "best_per_group_and_model": {
                f"{group}/{model}": trial.to_json_dict()
                for (group, model), trial in self.best_per_group_and_model.items()
            },
            "selected": self.selected.to_json_dict(),
        }


@dataclass(frozen=True)
class PersistencePolicyResult:
    candidates: dict[int, dict[str, float]]
    selected_persistence_samples: int

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "candidates": {str(k): v for k, v in self.candidates.items()},
            "selected_persistence_samples": self.selected_persistence_samples,
        }


@dataclass(frozen=True)
class ReferenceBaselineResult:
    rule: ThresholdRule
    validation_balanced_accuracy: float
    test_balanced_accuracy: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "measurement": self.rule.measurement,
            "threshold": self.rule.threshold,
            "fault_side": self.rule.fault_side,
            "train_balanced_accuracy": self.rule.train_balanced_accuracy,
            "validation_balanced_accuracy": self.validation_balanced_accuracy,
            "test_balanced_accuracy": self.test_balanced_accuracy,
        }


@dataclass(frozen=True)
class ExperimentResult:
    ablation: AblationResult
    persistence_policy: PersistencePolicyResult
    pipeline: Pipeline
    training_seconds: float
    validation_metrics: MulticlassMetrics
    test_metrics: MulticlassMetrics
    test_detection: DetectionSummary
    test_severity_recall: dict[str, list[GroupRecall]]
    test_ramp_recall: dict[str, list[GroupRecall]]
    test_false_positive_rate_healthy: float
    mean_prediction_latency_ms: float
    p95_prediction_latency_ms: float
    reference_baseline: ReferenceBaselineResult
    bootstrap_ci: dict[str, float]
    run_counts: dict[str, int]
    fault_run_counts: dict[str, dict[str, int]]
    severity_band_counts: dict[str, dict[str, int]]


def _run_counts(dataset: ExperimentDataset) -> dict[str, int]:
    counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0}
    for metadata in dataset.run_metadata.values():
        counts[metadata.split] = counts.get(metadata.split, 0) + 1
    return counts


def _fault_run_counts(dataset: ExperimentDataset) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {
        split: dict.fromkeys(FAULT_CLASSES, 0)
        for split in ("train", "validation", "test")
    }
    for metadata in dataset.run_metadata.values():
        if metadata.fault_class is not None:
            counts[metadata.split][metadata.fault_class] += 1
    return counts


def _severity_band_counts(dataset: ExperimentDataset) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {c: {} for c in FAULT_CLASSES}
    for metadata in dataset.run_metadata.values():
        if metadata.fault_class is None:
            continue
        band = band_for(metadata.configured_severity)
        if band is None:
            continue
        counts[metadata.fault_class][band] = (
            counts[metadata.fault_class].get(band, 0) + 1
        )
    return counts


def run_experiment(dataset: ExperimentDataset) -> ExperimentResult:
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")
    test_mask = dataset.split_mask("test")
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]
    y_test = dataset.y[test_mask]

    # --- 1. Feature-set ablation across both models (spec section 2) -------
    all_trials: list[SearchTrial] = []
    for group in FEATURE_GROUP_NAMES:
        x_train = dataset.X_group(group, train_mask)
        x_val = dataset.X_group(group, val_mask)
        all_trials += search_logistic_regression(x_train, y_train, x_val, y_val, group)
        all_trials += search_histogram_gb(x_train, y_train, x_val, y_val, group)

    best_per_group_and_model: dict[tuple[str, str], SearchTrial] = {}
    for group in FEATURE_GROUP_NAMES:
        for model_type in (LOGISTIC_REGRESSION, HISTOGRAM_GRADIENT_BOOSTING):
            matching = [
                t
                for t in all_trials
                if t.feature_group == group and t.model_type == model_type
            ]
            best_per_group_and_model[(group, model_type)] = best_trial(matching)

    selected = best_trial(all_trials)
    ablation = AblationResult(
        all_trials=all_trials,
        best_per_group_and_model=best_per_group_and_model,
        selected=selected,
    )

    # --- 2. Fit the selected configuration once, timed (spec section 7) ----
    x_train_selected = dataset.X_group(selected.feature_group, train_mask)
    x_val_selected = dataset.X_group(selected.feature_group, val_mask)
    x_test_selected = dataset.X_group(selected.feature_group, test_mask)

    pipeline = build_pipeline_for_trial(selected)
    start = time.perf_counter()
    fit_trial_pipeline(selected, pipeline, x_train_selected, y_train)
    training_seconds = time.perf_counter() - start

    val_predictions = pipeline.predict(x_val_selected)
    validation_metrics = compute_multiclass_metrics(y_val, val_predictions)

    # --- 3. Persistence-policy selection on validation only (spec section 8)
    candidates: dict[int, dict[str, float]] = {}
    for persistence_samples in PERSISTENCE_CANDIDATES:
        summary = evaluate_detection(
            dataset, val_mask, val_predictions, persistence_samples=persistence_samples
        )
        detected_fraction = (
            sum(1 for r in summary.run_results if r.detected) / len(summary.run_results)
            if summary.run_results
            else 0.0
        )
        candidates[persistence_samples] = {
            "detected_fraction": detected_fraction,
            "false_alarms_per_healthy_hour": summary.false_alarms_per_healthy_hour,
        }
    selected_persistence = max(
        PERSISTENCE_CANDIDATES,
        key=lambda p: (
            candidates[p]["detected_fraction"],
            -candidates[p]["false_alarms_per_healthy_hour"],
        ),
    )
    persistence_policy = PersistencePolicyResult(candidates, selected_persistence)

    # --- 4. Test evaluation, exactly once (spec section 7) ------------------
    test_predictions = pipeline.predict(x_test_selected)
    test_metrics = compute_multiclass_metrics(y_test, test_predictions)
    test_detection = evaluate_detection(
        dataset, test_mask, test_predictions, persistence_samples=selected_persistence
    )

    severity_labels_test = _severity_band_row_labels(dataset)[test_mask]
    ramp_labels_test = _ramp_row_labels(dataset)[test_mask]
    run_ids_test = dataset.run_ids[test_mask]

    test_severity_recall = {
        fault_class: recall_by_group(
            y_true=y_test,
            y_pred=test_predictions,
            group_labels=severity_labels_test,
            run_ids=run_ids_test,
            target_class=fault_class,
        )
        for fault_class in FAULT_CLASSES
    }
    test_ramp_recall = {
        fault_class: recall_by_group(
            y_true=y_test,
            y_pred=test_predictions,
            group_labels=ramp_labels_test,
            run_ids=run_ids_test,
            target_class=fault_class,
        )
        for fault_class in FAULT_CLASSES
    }

    healthy_mask = y_test == HEALTHY_LABEL
    test_false_positive_rate_healthy = (
        float((test_predictions[healthy_mask] != HEALTHY_LABEL).mean())
        if healthy_mask.any()
        else 0.0
    )

    mean_latency_ms, p95_latency_ms = measure_per_row_prediction_latency_ms(
        pipeline, x_test_selected
    )

    # --- 5. Optional reference baseline (spec section 10) -------------------
    x_train_a = dataset.X_group("A", train_mask)
    x_val_a = dataset.X_group("A", val_mask)
    x_test_a = dataset.X_group("A", test_mask)
    y_train_is_anomalous = y_train != HEALTHY_LABEL
    reference_rule = select_reference_threshold_rule(x_train_a, y_train_is_anomalous)
    reference_baseline = ReferenceBaselineResult(
        rule=reference_rule,
        validation_balanced_accuracy=evaluate_reference_rule(
            reference_rule, x_val_a, y_val != HEALTHY_LABEL
        ),
        test_balanced_accuracy=evaluate_reference_rule(
            reference_rule, x_test_a, y_test != HEALTHY_LABEL
        ),
    )

    # --- 6. Optional run-level bootstrap (spec section 12) ------------------
    bootstrap_ci = bootstrap_balanced_accuracy_ci(
        run_ids_test, y_test, test_predictions
    )

    return ExperimentResult(
        ablation=ablation,
        persistence_policy=persistence_policy,
        pipeline=pipeline,
        training_seconds=training_seconds,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        test_detection=test_detection,
        test_severity_recall=test_severity_recall,
        test_ramp_recall=test_ramp_recall,
        test_false_positive_rate_healthy=test_false_positive_rate_healthy,
        mean_prediction_latency_ms=mean_latency_ms,
        p95_prediction_latency_ms=p95_latency_ms,
        reference_baseline=reference_baseline,
        bootstrap_ci=bootstrap_ci,
        run_counts=_run_counts(dataset),
        fault_run_counts=_fault_run_counts(dataset),
        severity_band_counts=_severity_band_counts(dataset),
    )
