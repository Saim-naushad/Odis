"""`compare_models_on_cohort` specifications."""

from __future__ import annotations

import pytest

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.robustness.comparison import compare_models_on_cohort

from .conftest import make_evaluation


def test_balanced_accuracy_delta_is_robust_minus_original() -> None:
    original = make_evaluation(cohort_name="c", balanced_accuracy=0.70)
    robust = make_evaluation(cohort_name="c", balanced_accuracy=0.85)

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )

    assert comparison.balanced_accuracy.original_value == 0.70
    assert comparison.balanced_accuracy.robust_value == 0.85
    assert comparison.balanced_accuracy.absolute_change == pytest.approx(0.15)


def test_per_class_recall_deltas_cover_every_fault_class() -> None:
    original = make_evaluation(
        cohort_name="c",
        balanced_accuracy=0.7,
        per_class_recall={
            "cooling_degradation": 0.9,
            "hydrogen_supply_issue": 0.8,
            "sensor_anomaly": 0.6,
        },
    )
    robust = make_evaluation(
        cohort_name="c",
        balanced_accuracy=0.8,
        per_class_recall={
            "cooling_degradation": 0.7,
            "hydrogen_supply_issue": 0.85,
            "sensor_anomaly": 0.9,
        },
    )

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )

    assert set(comparison.per_class_recall) == set(FAULT_CLASSES)
    assert comparison.per_class_recall["cooling_degradation"].original_value == 0.9
    assert comparison.per_class_recall["cooling_degradation"].robust_value == 0.7
    delta = comparison.per_class_recall["sensor_anomaly"].absolute_change
    assert delta == pytest.approx(0.3)


def test_missed_run_counts_are_carried_through_as_deltas() -> None:
    original = make_evaluation(
        cohort_name="c", balanced_accuracy=0.7, correct_class_missed_run_count=3
    )
    robust = make_evaluation(
        cohort_name="c", balanced_accuracy=0.8, correct_class_missed_run_count=0
    )

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )

    assert comparison.correct_class_missed_run_count.original_value == 3
    assert comparison.correct_class_missed_run_count.robust_value == 0
    assert comparison.correct_class_missed_run_count.absolute_change == -3


def test_false_alert_rate_delta() -> None:
    original = make_evaluation(
        cohort_name="c",
        balanced_accuracy=0.7,
        false_alert_events_per_healthy_hour=10.0,
    )
    robust = make_evaluation(
        cohort_name="c", balanced_accuracy=0.8, false_alert_events_per_healthy_hour=1.0
    )

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )

    assert comparison.false_alert_events_per_healthy_hour.original_value == 10.0
    assert comparison.false_alert_events_per_healthy_hour.robust_value == 1.0


def test_valid_feature_coverage_delta() -> None:
    original = make_evaluation(
        cohort_name="c", balanced_accuracy=0.7, valid_feature_coverage=0.99
    )
    robust = make_evaluation(
        cohort_name="c", balanced_accuracy=0.8, valid_feature_coverage=0.95
    )

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )

    assert comparison.valid_feature_coverage.original_value == 0.99
    assert comparison.valid_feature_coverage.robust_value == 0.95
    assert comparison.valid_feature_coverage.absolute_change is not None
    assert comparison.valid_feature_coverage.absolute_change < 0


def test_to_json_dict_round_trips_every_field() -> None:
    original = make_evaluation(cohort_name="c", balanced_accuracy=0.7)
    robust = make_evaluation(cohort_name="c", balanced_accuracy=0.8)

    comparison = compare_models_on_cohort(
        "c", original, robust, fault_classes=FAULT_CLASSES
    )
    payload = comparison.to_json_dict()

    assert payload["cohort_name"] == "c"
    assert "balanced_accuracy" in payload
    assert "per_class_recall" in payload
    assert set(payload["per_class_recall"]) == set(FAULT_CLASSES)
