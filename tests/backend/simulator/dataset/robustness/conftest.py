"""Shared fixtures for PR174 robustness-module unit tests.

`make_evaluation` builds a minimal, directly-constructed `CohortEvaluation`
from just the handful of scalars each test cares about — real
`RowDiagnosisResult`/`AlertEvaluationResult`/`AvailabilityMetrics` objects
built from a tiny, explicit `run_results` list, rather than running the
full simulator+features+models pipeline for every comparison-logic test
case (that heavier, real-pipeline path is exercised once, end-to-end, in
`test_end_to_end.py`).
"""

from __future__ import annotations

from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    RunDetectionResult,
)
from backend.simulator.dataset.alert_policy.event_metrics import FalseAlertSummary
from backend.simulator.dataset.models.metrics import MulticlassMetrics
from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.availability_metrics import AvailabilityMetrics
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult
from backend.simulator.dataset.robustness.evaluation import CohortEvaluation

_CLASS_ORDER = (
    "healthy",
    "cooling_degradation",
    "hydrogen_supply_issue",
    "sensor_anomaly",
)


def make_evaluation(
    *,
    cohort_name: str,
    balanced_accuracy: float,
    healthy_false_positive_rate: float = 0.1,
    per_class_recall: dict[str, float] | None = None,
    valid_feature_coverage: float = 1.0,
    false_alert_events_per_healthy_hour: float = 0.5,
    correct_class_missed_run_count: int = 0,
    any_fault_missed_run_count: int = 0,
) -> CohortEvaluation:
    """A `CohortEvaluation` built directly from scalars, for exercising
    `compare_models_on_cohort`/`decide_promotion` without a real dataset.

    `correct_class_missed_run_count`/`any_fault_missed_run_count` are
    realized as that many `RunDetectionResult`s with the corresponding
    `*_detected=False`, plus one always-detected run — real
    `DetectionSummary` properties, not stand-ins.
    """
    recall_by_class = per_class_recall or {
        "cooling_degradation": 0.8,
        "hydrogen_supply_issue": 0.8,
        "sensor_anomaly": 0.8,
    }
    per_class = {
        "healthy": {
            "precision": 0.95,
            "recall": 1.0 - healthy_false_positive_rate,
            "f1": 0.9,
            "support": 100,
        },
        **{
            cls: {"precision": 0.7, "recall": recall, "f1": 0.7, "support": 20}
            for cls, recall in recall_by_class.items()
        },
    }
    multiclass_metrics = MulticlassMetrics(
        balanced_accuracy=balanced_accuracy,
        macro_precision=0.7,
        macro_recall=balanced_accuracy,
        macro_f1=0.7,
        per_class=per_class,
        confusion_matrix=[[0] * 4 for _ in range(4)],
        class_order=_CLASS_ORDER,
        support={cls: 20 for cls in _CLASS_ORDER},
    )
    diagnosis = RowDiagnosisResult(
        multiclass_metrics=multiclass_metrics,
        healthy_false_positive_rate=healthy_false_positive_rate,
        severity_band_recall={},
        ramp_stage_recall={},
    )

    run_results: list[RunDetectionResult] = []
    for i in range(any_fault_missed_run_count):
        run_results.append(
            RunDetectionResult(
                simulation_run_id=f"{cohort_name}-any-fault-missed-{i}",
                fault_class="cooling_degradation",
                fault_start_sim_seconds=100.0,
                correct_class_detected=False,
                correct_class_latency_seconds=None,
                any_fault_detected=False,
                any_fault_latency_seconds=None,
                any_fault_class_at_first_detection=None,
                incorrect_class_confirmed_before_correct=False,
                confirmed_active_at_onset=False,
                confirmed_class_at_onset=None,
            )
        )
    for i in range(correct_class_missed_run_count):
        run_results.append(
            RunDetectionResult(
                simulation_run_id=f"{cohort_name}-correct-class-missed-{i}",
                fault_class="cooling_degradation",
                fault_start_sim_seconds=100.0,
                correct_class_detected=False,
                correct_class_latency_seconds=None,
                any_fault_detected=True,
                any_fault_latency_seconds=110.0,
                any_fault_class_at_first_detection="hydrogen_supply_issue",
                incorrect_class_confirmed_before_correct=True,
                confirmed_active_at_onset=False,
                confirmed_class_at_onset=None,
            )
        )
    run_results.append(
        RunDetectionResult(
            simulation_run_id=f"{cohort_name}-detected",
            fault_class="cooling_degradation",
            fault_start_sim_seconds=100.0,
            correct_class_detected=True,
            correct_class_latency_seconds=120.0,
            any_fault_detected=True,
            any_fault_latency_seconds=120.0,
            any_fault_class_at_first_detection="cooling_degradation",
            incorrect_class_confirmed_before_correct=False,
            confirmed_active_at_onset=False,
            confirmed_class_at_onset=None,
        )
    )

    alerts = AlertEvaluationResult(
        detection=DetectionSummary(run_results=run_results),
        false_alerts=FalseAlertSummary(
            episodes=(
                [object()] if false_alert_events_per_healthy_hour > 0 else []  # type: ignore[list-item]
            ),
            false_anomalous_row_count=0,
            healthy_hours_evaluated=(
                1.0 / false_alert_events_per_healthy_hour
                if false_alert_events_per_healthy_hour > 0
                else 10.0
            ),
            healthy_run_ids_with_alert=set(),
            total_healthy_run_segments=10,
        ),
        incorrect_class_alert_run_count=0,
    )

    availability = AvailabilityMetrics(
        valid_feature_coverage=valid_feature_coverage,
        insufficient_data_rate=1.0 - valid_feature_coverage,
        insufficient_data_seconds_total=0.0,
        longest_consecutive_streak_rows=0,
        longest_consecutive_streak_seconds=0.0,
        affected_run_count=0,
        affected_asset_ids=(),
        reason_counts={},
        class_distribution={},
        stage_distribution={"ramp": 0, "post_ramp": 0, "not_in_fault_window": 0},
        ramp_unavailable_fraction=None,
        post_ramp_unavailable_fraction=None,
        detection_opportunities_interrupted=0,
    )

    return CohortEvaluation(
        cohort_name=cohort_name,
        row_count=100,
        run_count=len(run_results),
        diagnosis=diagnosis,
        alerts=alerts,
        availability=availability,
    )
