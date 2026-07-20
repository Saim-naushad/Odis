"""Operational alert-policy evaluation for an arbitrary cohort under the
frozen PR170 state-machine config (spec section 8, "Operational alert
behavior"; insufficient-data awareness added by PR173 spec section 6).

Uses `ood.gapped_alert_evaluation`'s insufficient-data-aware detection/
false-alert functions — themselves thin, gap-merging wrappers around the
unchanged PR170 event/episode logic (see that module's docstring for why
`alert_policy.detection.evaluate_detection`/`event_metrics.compute_false_
alert_summary` can't be called as-is here: they gather rows from an
already-loaded dataset with no notion of a rejected timestamp).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.detection import DetectionSummary
from backend.simulator.dataset.alert_policy.event_metrics import FalseAlertSummary
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.data_loading import InsufficientDataSummary
from backend.simulator.dataset.ood.gapped_alert_evaluation import (
    evaluate_gapped_detection,
    evaluate_gapped_false_alerts,
)

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
    insufficient_data: InsufficientDataSummary,
) -> AlertEvaluationResult:
    """Evaluate the frozen alert policy over the whole of `dataset` — the
    caller decides what `dataset` contains (an ID test split, or the whole
    OOD cohort treated as one external evaluation, per spec section 4).
    `insufficient_data` supplies the rejected timestamps this cohort's
    `dataset` never saw, so they can be replayed to the state machine as
    explicit `insufficient_data` rows rather than silent gaps."""
    detection = evaluate_gapped_detection(
        dataset, proba, insufficient_data, class_order, config
    )
    false_alerts = evaluate_gapped_false_alerts(
        dataset, proba, insufficient_data, class_order, config
    )
    incorrect_count = sum(
        1 for r in detection.run_results if r.incorrect_class_confirmed_before_correct
    )
    return AlertEvaluationResult(
        detection=detection,
        false_alerts=false_alerts,
        incorrect_class_alert_run_count=incorrect_count,
    )
