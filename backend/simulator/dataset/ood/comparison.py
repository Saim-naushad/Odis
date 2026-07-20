"""ID-vs-OOD comparison of the frozen model/policy's own metrics (spec
section 9).

"ID" here is the pilot's own held-out **test split**, scored through this
package's own `diagnosis_metrics`/`alert_metrics` functions — the same
code path used for OOD — rather than the PR168/PR170 report's original
numbers, so every comparison is apples-to-apples by construction. (The
recomputed numbers should closely match the original PR168/PR170 headline
figures; a large discrepancy would itself be a bug in this package, not a
data difference — see the reproducibility test.)

All shifts in `pem_faults_ood_v1.json` are applied simultaneously (higher
load, hotter initial state, later fault onset, doubled sensor noise) —
this comparison cannot and does not attempt to attribute degradation to
any single shift. Any shift-level explanation offered in the rendered
report is an inference, not a controlled result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult


@dataclass(frozen=True)
class MetricDelta:
    id_value: float | None
    ood_value: float | None

    @property
    def absolute_change(self) -> float | None:
        if self.id_value is None or self.ood_value is None:
            return None
        return self.ood_value - self.id_value

    @property
    def relative_change(self) -> float | None:
        if (
            self.id_value is None
            or self.ood_value is None
            or abs(self.id_value) < 1e-12
        ):
            return None
        return (self.ood_value - self.id_value) / abs(self.id_value)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id_value,
            "ood": self.ood_value,
            "absolute_change": self.absolute_change,
            "relative_change": self.relative_change,
        }


@dataclass(frozen=True)
class GeneralizationComparison:
    balanced_accuracy: MetricDelta
    macro_f1: MetricDelta
    healthy_false_positive_rate: MetricDelta
    per_class_recall: dict[str, MetricDelta]
    false_alert_events_per_healthy_hour: MetricDelta
    any_fault_missed_run_count: MetricDelta
    correct_class_missed_run_count: MetricDelta
    median_correct_class_latency_seconds: MetricDelta
    detected_within_120s: MetricDelta

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "balanced_accuracy": self.balanced_accuracy.to_json_dict(),
            "macro_f1": self.macro_f1.to_json_dict(),
            "healthy_false_positive_rate": (
                self.healthy_false_positive_rate.to_json_dict()
            ),
            "per_class_recall": {
                cls: delta.to_json_dict()
                for cls, delta in self.per_class_recall.items()
            },
            "false_alert_events_per_healthy_hour": (
                self.false_alert_events_per_healthy_hour.to_json_dict()
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
            "detected_within_120s": self.detected_within_120s.to_json_dict(),
        }


def compare_id_vs_ood(
    *,
    id_diagnosis: RowDiagnosisResult,
    ood_diagnosis: RowDiagnosisResult,
    id_alerts: AlertEvaluationResult,
    ood_alerts: AlertEvaluationResult,
    fault_classes: tuple[str, ...],
) -> GeneralizationComparison:
    def recall(result: RowDiagnosisResult, cls: str) -> float | None:
        entry = result.multiclass_metrics.per_class.get(cls)
        return entry["recall"] if entry else None

    return GeneralizationComparison(
        balanced_accuracy=MetricDelta(
            id_diagnosis.multiclass_metrics.balanced_accuracy,
            ood_diagnosis.multiclass_metrics.balanced_accuracy,
        ),
        macro_f1=MetricDelta(
            id_diagnosis.multiclass_metrics.macro_f1,
            ood_diagnosis.multiclass_metrics.macro_f1,
        ),
        healthy_false_positive_rate=MetricDelta(
            id_diagnosis.healthy_false_positive_rate,
            ood_diagnosis.healthy_false_positive_rate,
        ),
        per_class_recall={
            cls: MetricDelta(recall(id_diagnosis, cls), recall(ood_diagnosis, cls))
            for cls in fault_classes
        },
        false_alert_events_per_healthy_hour=MetricDelta(
            id_alerts.false_alerts.false_alert_events_per_healthy_hour,
            ood_alerts.false_alerts.false_alert_events_per_healthy_hour,
        ),
        any_fault_missed_run_count=MetricDelta(
            len(id_alerts.detection.any_fault_missed_runs),
            len(ood_alerts.detection.any_fault_missed_runs),
        ),
        correct_class_missed_run_count=MetricDelta(
            len(id_alerts.detection.correct_class_missed_runs),
            len(ood_alerts.detection.correct_class_missed_runs),
        ),
        median_correct_class_latency_seconds=MetricDelta(
            id_alerts.detection.median_correct_class_latency_seconds,
            ood_alerts.detection.median_correct_class_latency_seconds,
        ),
        detected_within_120s=MetricDelta(
            id_alerts.detection.detected_within_seconds(120),
            ood_alerts.detection.detected_within_seconds(120),
        ),
    )
