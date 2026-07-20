"""Operational alert-policy evaluation for an arbitrary cohort under the
frozen PR170 state-machine config (spec section 8, "Operational alert
behavior").

Reuses `alert_policy.detection.evaluate_detection` (state-machine-based
run detection/latency) and `alert_policy.event_metrics.compute_false_alert_
summary` (false-alert episodes on genuinely healthy segments) unchanged —
this module only supplies an all-rows mask (an OOD/ID cohort here is
evaluated whole, not split further) and adds the extra 240s detection
threshold and an incorrect-class-alert count the frozen functions don't
already expose as a single number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    evaluate_detection,
)
from backend.simulator.dataset.alert_policy.event_metrics import (
    FalseAlertSummary,
    compute_false_alert_summary,
)
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset

EXTRA_DETECTION_LATENCY_THRESHOLD_SECONDS = 240


@dataclass(frozen=True)
class AlertEvaluationResult:
    detection: DetectionSummary
    false_alerts: FalseAlertSummary
    incorrect_class_alert_run_count: int
    """Runs where an incorrect fault class was confirmed at or before the
    correct class (`RunDetectionResult.incorrect_class_confirmed_before_
    correct`)."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "detection": self.detection.to_json_dict(),
            "detected_within_240s": self.detection.detected_within_seconds(
                EXTRA_DETECTION_LATENCY_THRESHOLD_SECONDS
            ),
            "false_alerts": self.false_alerts.to_json_dict(),
            "incorrect_class_alert_run_count": self.incorrect_class_alert_run_count,
        }


def evaluate_alert_policy(
    dataset: ExperimentDataset,
    proba: np.ndarray,
    class_order: tuple[str, ...],
    config: StateMachineConfig,
) -> AlertEvaluationResult:
    """Evaluate the frozen alert policy over the whole of `dataset` — the
    caller decides what `dataset` contains (an ID test split, or the whole
    OOD cohort treated as one external evaluation, per spec section 4)."""
    mask = np.ones(len(dataset.y), dtype=bool)
    detection = evaluate_detection(dataset, mask, proba, class_order, config)
    false_alerts = compute_false_alert_summary(
        dataset, mask, proba, class_order, config
    )
    incorrect_count = sum(
        1 for r in detection.run_results if r.incorrect_class_confirmed_before_correct
    )
    return AlertEvaluationResult(
        detection=detection,
        false_alerts=false_alerts,
        incorrect_class_alert_run_count=incorrect_count,
    )
