"""Row-level abstention: converts calibrated probabilities into a
diagnosis or `"uncertain"` (PR169 spec section 4).

A row's diagnosis is the argmax calibrated class whenever
`max(calibrated_probability) >= confidence_threshold`, and
`config.UNCERTAIN_LABEL` otherwise — never a partial/soft output, and
never silently defaulting to `"healthy"` (an abstention is not the same
claim as a healthy diagnosis, see `coverage_metrics`'s explicit
`uncertain_rate_on_healthy_rows` vs. `healthy_false_positive_rate` split).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.calibration.config import UNCERTAIN_LABEL
from backend.simulator.dataset.models.config import HEALTHY_LABEL, PRIMARY_CLASSES
from backend.simulator.dataset.models.metrics import compute_multiclass_metrics


def diagnose(
    proba: np.ndarray, class_order: tuple[str, ...], *, confidence_threshold: float
) -> np.ndarray:
    """One diagnosis string per row: the argmax class, or `"uncertain"`
    when that class's probability falls below `confidence_threshold`."""
    predicted_index = proba.argmax(axis=1)
    confidence = proba.max(axis=1)
    predicted_labels = np.array(class_order, dtype=object)[predicted_index]
    return np.where(
        confidence >= confidence_threshold, predicted_labels, UNCERTAIN_LABEL
    )


@dataclass(frozen=True)
class CoverageMetrics:
    confidence_threshold: float
    coverage: float
    selective_balanced_accuracy: float
    selective_macro_f1: float
    healthy_false_positive_rate: float
    uncertain_rate_healthy: float
    uncertain_rate_active_fault: float
    per_class_retained_coverage: dict[str, float]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "coverage": self.coverage,
            "selective_balanced_accuracy": self.selective_balanced_accuracy,
            "selective_macro_f1": self.selective_macro_f1,
            "healthy_false_positive_rate": self.healthy_false_positive_rate,
            "uncertain_rate_healthy": self.uncertain_rate_healthy,
            "uncertain_rate_active_fault": self.uncertain_rate_active_fault,
            "per_class_retained_coverage": self.per_class_retained_coverage,
        }


def compute_coverage_metrics(
    y_true: np.ndarray, diagnosis: np.ndarray, *, confidence_threshold: float
) -> CoverageMetrics:
    covered = diagnosis != UNCERTAIN_LABEL
    coverage = float(covered.mean()) if len(diagnosis) else 0.0

    if covered.any():
        selective = compute_multiclass_metrics(y_true[covered], diagnosis[covered])
        selective_balanced_accuracy = selective.balanced_accuracy
        selective_macro_f1 = selective.macro_f1
    else:
        selective_balanced_accuracy = 0.0
        selective_macro_f1 = 0.0

    healthy_mask = y_true == HEALTHY_LABEL
    if healthy_mask.any():
        healthy_diagnosis = diagnosis[healthy_mask]
        false_positive = (healthy_diagnosis != HEALTHY_LABEL) & (
            healthy_diagnosis != UNCERTAIN_LABEL
        )
        healthy_false_positive_rate = float(false_positive.mean())
        uncertain_rate_healthy = float((healthy_diagnosis == UNCERTAIN_LABEL).mean())
    else:
        healthy_false_positive_rate = 0.0
        uncertain_rate_healthy = 0.0

    active_fault_mask = y_true != HEALTHY_LABEL
    uncertain_rate_active_fault = (
        float((diagnosis[active_fault_mask] == UNCERTAIN_LABEL).mean())
        if active_fault_mask.any()
        else 0.0
    )

    per_class_retained_coverage = {}
    for class_label in PRIMARY_CLASSES:
        class_mask = y_true == class_label
        if not class_mask.any():
            per_class_retained_coverage[class_label] = 0.0
            continue
        per_class_retained_coverage[class_label] = float(
            (diagnosis[class_mask] != UNCERTAIN_LABEL).mean()
        )

    return CoverageMetrics(
        confidence_threshold=confidence_threshold,
        coverage=coverage,
        selective_balanced_accuracy=selective_balanced_accuracy,
        selective_macro_f1=selective_macro_f1,
        healthy_false_positive_rate=healthy_false_positive_rate,
        uncertain_rate_healthy=uncertain_rate_healthy,
        uncertain_rate_active_fault=uncertain_rate_active_fault,
        per_class_retained_coverage=per_class_retained_coverage,
    )
