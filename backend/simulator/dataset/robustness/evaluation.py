"""Scores one frozen model artifact on one cohort, reusing PR171/173's
`ood` package metric functions unchanged.

This module never recomputes diagnosis, alert, or availability metrics
itself — `ood.diagnosis_metrics`, `ood.alert_metrics`, and
`ood.availability_metrics` are already generic over "some pipeline scored
on some `ExperimentDataset`," with no assumption baked in about which
model produced the pipeline or which cohort the dataset came from. This
module's only job is to load a cohort (optionally narrowed to one split)
and call them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.ood.alert_metrics import (
    AlertEvaluationResult,
    evaluate_alert_policy,
)
from backend.simulator.dataset.ood.availability_metrics import (
    AvailabilityMetrics,
    compute_availability_metrics,
)
from backend.simulator.dataset.ood.data_loading import (
    filter_experiment_dataset,
    filter_insufficient_data_summary_to_runs,
    load_ood_experiment_dataset,
)
from backend.simulator.dataset.ood.diagnosis_metrics import (
    RowDiagnosisResult,
    evaluate_row_diagnosis,
    predict,
)
from backend.simulator.dataset.robustness.artifacts import ModelArtifacts
from backend.simulator.dataset.robustness.config import FROZEN_ALERT_POLICY


@dataclass(frozen=True)
class CohortEvaluation:
    cohort_name: str
    row_count: int
    run_count: int
    diagnosis: RowDiagnosisResult
    alerts: AlertEvaluationResult
    availability: AvailabilityMetrics

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cohort_name": self.cohort_name,
            "row_count": self.row_count,
            "run_count": self.run_count,
            "diagnosis": self.diagnosis.to_json_dict(),
            "alerts": self.alerts.to_json_dict(),
            "availability": self.availability.to_json_dict(),
        }


def evaluate_model_on_cohort(
    artifacts: ModelArtifacts,
    features_dir: Path,
    *,
    cohort_name: str,
    dataset_dir: Path | None = None,
    split: str | None = None,
) -> CohortEvaluation:
    """Score `artifacts.pipeline` on the cohort at `features_dir`.

    `split=None` scores the entire cohort dataset (every one of PR171/172's
    external shift/OOD cohorts is used this way — none of them were ever
    part of either model's training data, so there is no held-out subset to
    select). `split="test"` narrows to one named split first — used for the
    pilot cohort, and for a model's own internal test split, so a model is
    never scored on rows it saw during fitting.
    """
    dataset, insufficient_data = load_ood_experiment_dataset(features_dir, dataset_dir)
    if split is not None:
        mask = dataset.split_mask(split)
        run_ids = set(dataset.run_ids[mask].tolist())
        dataset = filter_experiment_dataset(dataset, mask)
        insufficient_data = filter_insufficient_data_summary_to_runs(
            insufficient_data, run_ids, valid_row_count=len(dataset.y)
        )

    predictions = predict(dataset, artifacts.pipeline, artifacts.feature_group)
    diagnosis = evaluate_row_diagnosis(
        dataset, predictions, fault_classes=FAULT_CLASSES
    )
    alerts = evaluate_alert_policy(
        dataset,
        predictions.proba,
        artifacts.class_order,
        FROZEN_ALERT_POLICY,
        insufficient_data,
    )
    resolved_dataset_dir = dataset_dir or Path(
        dataset.manifest["source_dataset"]["directory"]
    )
    availability = compute_availability_metrics(
        dataset, insufficient_data, resolved_dataset_dir
    )

    return CohortEvaluation(
        cohort_name=cohort_name,
        row_count=len(dataset.y),
        # `run_metadata` is never narrowed by `filter_experiment_dataset`
        # (it's per-run, not per-row) — derive the run count actually
        # present from the filtered `run_ids` column instead.
        run_count=len(set(dataset.run_ids.tolist())),
        diagnosis=diagnosis,
        alerts=alerts,
        availability=availability,
    )
