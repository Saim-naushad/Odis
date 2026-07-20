"""Row-level diagnosis metrics for the frozen pipeline on an arbitrary
evaluation cohort (spec section 8, "Row-level diagnosis").

Every function here is pure: given an already-loaded `ExperimentDataset`
and already-loaded frozen pipeline/class order, it predicts and scores —
no fitting, no thresholds tuned from what it observes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.metrics import (
    MulticlassMetrics,
    compute_multiclass_metrics,
)
from backend.simulator.dataset.models.severity import (
    GroupRecall,
    ramp_row_labels,
    recall_by_group,
    severity_band_row_labels,
)


@dataclass(frozen=True)
class RowPredictions:
    proba: np.ndarray
    """Aligned to `classes` column order (`pipeline.classes_`)."""
    classes: tuple[str, ...]
    y_pred: np.ndarray


def predict(
    dataset: ExperimentDataset, pipeline: Pipeline, feature_group: str
) -> RowPredictions:
    x = dataset.X_group(feature_group)
    proba = pipeline.predict_proba(x)
    y_pred = pipeline.predict(x)
    classes = tuple(pipeline.named_steps["classifier"].classes_)
    return RowPredictions(proba=proba, classes=classes, y_pred=y_pred)


def healthy_false_positive_rate(
    dataset: ExperimentDataset, y_pred: np.ndarray
) -> float:
    """Of every row whose true label is healthy, the fraction predicted as
    some non-healthy class — the row-level false-positive rate a fixed
    per-row threshold (no persistence) would see."""
    is_healthy = dataset.y == HEALTHY_LABEL
    if not is_healthy.any():
        return 0.0
    return float((y_pred[is_healthy] != HEALTHY_LABEL).mean())


@dataclass(frozen=True)
class RowDiagnosisResult:
    multiclass_metrics: MulticlassMetrics
    healthy_false_positive_rate: float
    severity_band_recall: dict[str, list[GroupRecall]]
    """Per fault class, recall broken down by configured-severity band."""
    ramp_stage_recall: dict[str, list[GroupRecall]]
    """Per fault class, recall broken down by ramp vs. post_ramp stage."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "multiclass_metrics": self.multiclass_metrics.to_json_dict(),
            "healthy_false_positive_rate": self.healthy_false_positive_rate,
            "severity_band_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in self.severity_band_recall.items()
            },
            "ramp_stage_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in self.ramp_stage_recall.items()
            },
        }


def evaluate_row_diagnosis(
    dataset: ExperimentDataset,
    predictions: RowPredictions,
    *,
    fault_classes: tuple[str, ...],
) -> RowDiagnosisResult:
    multiclass_metrics = compute_multiclass_metrics(
        dataset.y, predictions.y_pred, class_order=predictions.classes
    )
    fp_rate = healthy_false_positive_rate(dataset, predictions.y_pred)

    severity_labels = severity_band_row_labels(dataset)
    ramp_labels = ramp_row_labels(dataset)
    severity_band_recall = {
        cls: recall_by_group(
            y_true=dataset.y,
            y_pred=predictions.y_pred,
            group_labels=severity_labels,
            run_ids=dataset.run_ids,
            target_class=cls,
        )
        for cls in fault_classes
    }
    ramp_stage_recall = {
        cls: recall_by_group(
            y_true=dataset.y,
            y_pred=predictions.y_pred,
            group_labels=ramp_labels,
            run_ids=dataset.run_ids,
            target_class=cls,
        )
        for cls in fault_classes
    }
    return RowDiagnosisResult(
        multiclass_metrics=multiclass_metrics,
        healthy_false_positive_rate=fp_rate,
        severity_band_recall=severity_band_recall,
        ramp_stage_recall=ramp_stage_recall,
    )
