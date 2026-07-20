"""OOD verdict thresholds (spec section 12/14) — pinned against directly
constructed metric objects so the three bands are tested independently of
any real dataset.
"""

from __future__ import annotations

from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    RunDetectionResult,
)
from backend.simulator.dataset.alert_policy.event_metrics import (
    FalseAlertSummary,
    FalseEpisode,
)
from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.models.metrics import MulticlassMetrics
from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.comparison import (
    GeneralizationComparison,
    MetricDelta,
)
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult
from backend.simulator.dataset.ood.verdict import determine_ood_verdict

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")


def _multiclass_metrics(
    balanced_accuracy: float, recalls: dict[str, float]
) -> MulticlassMetrics:
    per_class = {
        cls: {
            "precision": 0.5,
            "recall": recalls.get(cls, 0.8),
            "f1": 0.5,
            "support": 10,
        }
        for cls in _CLASSES
    }
    return MulticlassMetrics(
        balanced_accuracy=balanced_accuracy,
        macro_precision=0.5,
        macro_recall=balanced_accuracy,
        macro_f1=0.5,
        per_class=per_class,
        confusion_matrix=[[0] * 4 for _ in range(4)],
        class_order=_CLASSES,
        support={cls: 10 for cls in _CLASSES},
    )


def _diagnosis(
    balanced_accuracy: float, recalls: dict[str, float]
) -> RowDiagnosisResult:
    return RowDiagnosisResult(
        multiclass_metrics=_multiclass_metrics(balanced_accuracy, recalls),
        healthy_false_positive_rate=0.1,
        severity_band_recall={},
        ramp_stage_recall={},
    )


def _alerts(
    *,
    false_alert_rate_per_hour: float,
    missed_fraction_by_class: dict[str, float],
) -> AlertEvaluationResult:
    run_results: list[RunDetectionResult] = []
    for cls, fraction in missed_fraction_by_class.items():
        total = 10
        missed = round(fraction * total)
        for i in range(total):
            detected = i >= missed
            run_results.append(
                RunDetectionResult(
                    simulation_run_id=f"{cls}-{i}",
                    fault_class=cls,
                    fault_start_sim_seconds=100.0,
                    correct_class_detected=detected,
                    correct_class_latency_seconds=50.0 if detected else None,
                    any_fault_detected=detected,
                    any_fault_latency_seconds=50.0 if detected else None,
                    any_fault_class_at_first_detection=cls if detected else None,
                    incorrect_class_confirmed_before_correct=False,
                    confirmed_active_at_onset=False,
                    confirmed_class_at_onset=None,
                )
            )
    detection = DetectionSummary(run_results=run_results)

    # `false_alert_events_per_healthy_hour` is `len(episodes) /
    # healthy_hours_evaluated` — fixing hours at 1.0 and synthesizing that
    # many episodes hits the target rate directly.
    episode_count = round(false_alert_rate_per_hour)
    episodes = [
        FalseEpisode(
            simulation_run_id=f"healthy-{i}",
            fault_class="cooling_degradation",
            start_elapsed_sim_seconds=0.0,
            end_elapsed_sim_seconds=60.0,
            censored=False,
        )
        for i in range(episode_count)
    ]
    false_alerts = FalseAlertSummary(
        episodes=episodes,
        false_anomalous_row_count=0,
        healthy_hours_evaluated=1.0,
        healthy_run_ids_with_alert=set(),
        total_healthy_run_segments=1,
    )
    return AlertEvaluationResult(
        detection=detection,
        false_alerts=false_alerts,
        incorrect_class_alert_run_count=0,
    )


def _comparison(balanced_accuracy_drop: float) -> GeneralizationComparison:
    id_value = 0.85
    ood_value = id_value - balanced_accuracy_drop
    zero_delta = MetricDelta(id_value=0.0, ood_value=0.0)
    return GeneralizationComparison(
        balanced_accuracy=MetricDelta(id_value=id_value, ood_value=ood_value),
        macro_f1=zero_delta,
        healthy_false_positive_rate=zero_delta,
        per_class_recall={cls: zero_delta for cls in FAULT_CLASSES},
        false_alert_events_per_healthy_hour=zero_delta,
        any_fault_missed_run_count=zero_delta,
        correct_class_missed_run_count=zero_delta,
        median_correct_class_latency_seconds=zero_delta,
        detected_within_120s=zero_delta,
    )


def test_generalizes_acceptably() -> None:
    diagnosis = _diagnosis(0.80, {cls: 0.85 for cls in FAULT_CLASSES})
    alerts = _alerts(
        false_alert_rate_per_hour=0.5,
        missed_fraction_by_class={cls: 0.0 for cls in FAULT_CLASSES},
    )
    comparison = _comparison(balanced_accuracy_drop=0.05)

    result = determine_ood_verdict(
        ood_diagnosis=diagnosis,
        ood_alerts=alerts,
        comparison=comparison,
        fault_classes=FAULT_CLASSES,
    )
    assert result.verdict == "GENERALIZES ACCEPTABLY TO OOD V1"


def test_generalizes_with_material_degradation() -> None:
    diagnosis = _diagnosis(0.65, {cls: 0.6 for cls in FAULT_CLASSES})
    alerts = _alerts(
        false_alert_rate_per_hour=2.0,
        missed_fraction_by_class={cls: 0.3 for cls in FAULT_CLASSES},
    )
    comparison = _comparison(balanced_accuracy_drop=0.20)

    result = determine_ood_verdict(
        ood_diagnosis=diagnosis,
        ood_alerts=alerts,
        comparison=comparison,
        fault_classes=FAULT_CLASSES,
    )
    assert result.verdict == "GENERALIZES WITH MATERIAL DEGRADATION"


def test_does_not_generalize_on_class_collapse() -> None:
    recalls = {cls: 0.85 for cls in FAULT_CLASSES}
    recalls["cooling_degradation"] = 0.1
    diagnosis = _diagnosis(0.60, recalls)
    alerts = _alerts(
        false_alert_rate_per_hour=0.5,
        missed_fraction_by_class={cls: 0.0 for cls in FAULT_CLASSES},
    )
    comparison = _comparison(balanced_accuracy_drop=0.25)

    result = determine_ood_verdict(
        ood_diagnosis=diagnosis,
        ood_alerts=alerts,
        comparison=comparison,
        fault_classes=FAULT_CLASSES,
    )
    assert result.verdict == "DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED"
    assert any("collapsed" in reason for reason in result.reasons)


def test_does_not_generalize_on_excessive_false_alerts() -> None:
    diagnosis = _diagnosis(0.80, {cls: 0.85 for cls in FAULT_CLASSES})
    alerts = _alerts(
        false_alert_rate_per_hour=10.0,
        missed_fraction_by_class={cls: 0.0 for cls in FAULT_CLASSES},
    )
    comparison = _comparison(balanced_accuracy_drop=0.05)

    result = determine_ood_verdict(
        ood_diagnosis=diagnosis,
        ood_alerts=alerts,
        comparison=comparison,
        fault_classes=FAULT_CLASSES,
    )
    assert result.verdict == "DOES NOT GENERALIZE — MODEL OR FEATURE REVISION REQUIRED"
