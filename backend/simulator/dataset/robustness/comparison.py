"""Original-vs-robust comparison of two models' metrics on the same cohort
(spec section 10).

Deliberately its own axis, distinct from `ood.comparison.compare_id_vs_ood`
(which compares one frozen model's ID split against one OOD cohort): here
both sides are the *same* cohort, scored by two different frozen models.
Reusing `ood.comparison.MetricDelta`'s `id_value`/`ood_value` field names
for this axis would misread as an ID/OOD split rather than a model
comparison, so this module defines its own equivalently-shaped `ModelDelta`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.robustness.evaluation import CohortEvaluation


@dataclass(frozen=True)
class ModelDelta:
    original_value: float | None
    robust_value: float | None

    @property
    def absolute_change(self) -> float | None:
        if self.original_value is None or self.robust_value is None:
            return None
        return self.robust_value - self.original_value

    @property
    def relative_change(self) -> float | None:
        if (
            self.original_value is None
            or self.robust_value is None
            or abs(self.original_value) < 1e-12
        ):
            return None
        return (self.robust_value - self.original_value) / abs(self.original_value)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "original": self.original_value,
            "robust": self.robust_value,
            "absolute_change": self.absolute_change,
            "relative_change": self.relative_change,
        }


@dataclass(frozen=True)
class CohortComparison:
    cohort_name: str
    balanced_accuracy: ModelDelta
    macro_f1: ModelDelta
    healthy_false_positive_rate: ModelDelta
    per_class_recall: dict[str, ModelDelta]
    per_class_precision: dict[str, ModelDelta]
    valid_feature_coverage: ModelDelta
    false_alert_events_per_healthy_hour: ModelDelta
    healthy_runs_with_alert_count: ModelDelta
    any_fault_missed_run_count: ModelDelta
    correct_class_missed_run_count: ModelDelta
    median_correct_class_latency_seconds: ModelDelta
    detected_within_60s: ModelDelta
    detected_within_120s: ModelDelta
    detected_within_240s: ModelDelta
    insufficient_data_rate: ModelDelta

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cohort_name": self.cohort_name,
            "balanced_accuracy": self.balanced_accuracy.to_json_dict(),
            "macro_f1": self.macro_f1.to_json_dict(),
            "healthy_false_positive_rate": (
                self.healthy_false_positive_rate.to_json_dict()
            ),
            "per_class_recall": {
                cls: delta.to_json_dict()
                for cls, delta in self.per_class_recall.items()
            },
            "per_class_precision": {
                cls: delta.to_json_dict()
                for cls, delta in self.per_class_precision.items()
            },
            "valid_feature_coverage": self.valid_feature_coverage.to_json_dict(),
            "false_alert_events_per_healthy_hour": (
                self.false_alert_events_per_healthy_hour.to_json_dict()
            ),
            "healthy_runs_with_alert_count": (
                self.healthy_runs_with_alert_count.to_json_dict()
            ),
            "any_fault_missed_run_count": (
                self.any_fault_missed_run_count.to_json_dict()
            ),
            "correct_class_missed_run_count": (
                self.correct_class_missed_run_count.to_json_dict()
            ),
            "median_correct_class_latency_seconds": (
                self.median_correct_class_latency_seconds.to_json_dict()
            ),
            "detected_within_60s": self.detected_within_60s.to_json_dict(),
            "detected_within_120s": self.detected_within_120s.to_json_dict(),
            "detected_within_240s": self.detected_within_240s.to_json_dict(),
            "insufficient_data_rate": self.insufficient_data_rate.to_json_dict(),
        }


def compare_models_on_cohort(
    cohort_name: str,
    original: CohortEvaluation,
    robust: CohortEvaluation,
    *,
    fault_classes: tuple[str, ...],
) -> CohortComparison:
    def recall(evaluation: CohortEvaluation, cls: str) -> float | None:
        entry = evaluation.diagnosis.multiclass_metrics.per_class.get(cls)
        return entry["recall"] if entry else None

    def precision(evaluation: CohortEvaluation, cls: str) -> float | None:
        entry = evaluation.diagnosis.multiclass_metrics.per_class.get(cls)
        return entry["precision"] if entry else None

    return CohortComparison(
        cohort_name=cohort_name,
        balanced_accuracy=ModelDelta(
            original.diagnosis.multiclass_metrics.balanced_accuracy,
            robust.diagnosis.multiclass_metrics.balanced_accuracy,
        ),
        macro_f1=ModelDelta(
            original.diagnosis.multiclass_metrics.macro_f1,
            robust.diagnosis.multiclass_metrics.macro_f1,
        ),
        healthy_false_positive_rate=ModelDelta(
            original.diagnosis.healthy_false_positive_rate,
            robust.diagnosis.healthy_false_positive_rate,
        ),
        per_class_recall={
            cls: ModelDelta(recall(original, cls), recall(robust, cls))
            for cls in fault_classes
        },
        per_class_precision={
            cls: ModelDelta(precision(original, cls), precision(robust, cls))
            for cls in fault_classes
        },
        valid_feature_coverage=ModelDelta(
            original.availability.valid_feature_coverage,
            robust.availability.valid_feature_coverage,
        ),
        false_alert_events_per_healthy_hour=ModelDelta(
            original.alerts.false_alerts.false_alert_events_per_healthy_hour,
            robust.alerts.false_alerts.false_alert_events_per_healthy_hour,
        ),
        healthy_runs_with_alert_count=ModelDelta(
            len(original.alerts.false_alerts.healthy_run_ids_with_alert),
            len(robust.alerts.false_alerts.healthy_run_ids_with_alert),
        ),
        any_fault_missed_run_count=ModelDelta(
            len(original.alerts.detection.any_fault_missed_runs),
            len(robust.alerts.detection.any_fault_missed_runs),
        ),
        correct_class_missed_run_count=ModelDelta(
            len(original.alerts.detection.correct_class_missed_runs),
            len(robust.alerts.detection.correct_class_missed_runs),
        ),
        median_correct_class_latency_seconds=ModelDelta(
            original.alerts.detection.median_correct_class_latency_seconds,
            robust.alerts.detection.median_correct_class_latency_seconds,
        ),
        detected_within_60s=ModelDelta(
            original.alerts.detection.detected_within_seconds(60),
            robust.alerts.detection.detected_within_seconds(60),
        ),
        detected_within_120s=ModelDelta(
            original.alerts.detection.detected_within_seconds(120),
            robust.alerts.detection.detected_within_seconds(120),
        ),
        detected_within_240s=ModelDelta(
            original.alerts.detection.detected_within_seconds(240),
            robust.alerts.detection.detected_within_seconds(240),
        ),
        insufficient_data_rate=ModelDelta(
            original.availability.insufficient_data_rate,
            robust.availability.insufficient_data_rate,
        ),
    )
