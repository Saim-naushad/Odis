"""Metrics correctness on known fixtures (PR168 spec section 13, "Metrics"
test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.models.config import PRIMARY_CLASSES
from backend.simulator.dataset.models.metrics import compute_multiclass_metrics


def test_perfect_predictions_give_balanced_accuracy_one() -> None:
    # All four classes present with at least one sample, so a perfect
    # prediction set gives every class F1=1.0 and macro_f1=1.0 too.
    labels = [
        "healthy", "healthy", "cooling_degradation",
        "sensor_anomaly", "hydrogen_supply_issue",
    ]
    y_true = np.array(labels)
    y_pred = np.array(labels)
    result = compute_multiclass_metrics(y_true, y_pred)
    assert result.balanced_accuracy == 1.0
    assert result.macro_f1 == 1.0
    assert result.per_class["healthy"]["recall"] == 1.0


def test_absent_class_reports_zero_support_not_missing() -> None:
    y_true = np.array(["healthy", "healthy", "cooling_degradation", "sensor_anomaly"])
    y_pred = np.array(["healthy", "healthy", "cooling_degradation", "sensor_anomaly"])
    result = compute_multiclass_metrics(y_true, y_pred)
    # hydrogen_supply_issue is absent from this slice entirely — it must
    # still appear in per_class with zero support, not vanish, so a
    # feature-set/model comparison table never silently drops a column.
    assert result.per_class["hydrogen_supply_issue"]["support"] == 0
    assert result.per_class["hydrogen_supply_issue"]["f1"] == 0.0


def test_known_confusion_gives_expected_per_class_metrics() -> None:
    # 4 healthy (3 correct, 1 called cooling_degradation) and 2
    # cooling_degradation (1 correct, 1 called healthy).
    y_true = np.array(
        ["healthy", "healthy", "healthy", "healthy",
         "cooling_degradation", "cooling_degradation"]
    )
    y_pred = np.array(
        ["healthy", "healthy", "healthy",
         "cooling_degradation", "cooling_degradation", "healthy"]
    )
    result = compute_multiclass_metrics(y_true, y_pred)

    # healthy: TP=3, FN=1 (recall 0.75); predicted 4 times, 3 correct (precision 0.75)
    assert result.per_class["healthy"]["recall"] == 0.75
    assert result.per_class["healthy"]["precision"] == 0.75
    # cooling_degradation: TP=1, FN=1 (recall 0.5); predicted twice, 1 correct
    assert result.per_class["cooling_degradation"]["recall"] == 0.5
    assert result.per_class["cooling_degradation"]["precision"] == 0.5
    assert result.support["healthy"] == 4
    assert result.support["cooling_degradation"] == 2
    # balanced accuracy = mean of per-class recall over classes with support > 0
    # (sklearn averages over all labels passed; absent classes contribute
    # recall 0 with zero_division=0, pulling the average down — verify the
    # raw confusion matrix instead of re-deriving sklearn's own formula).
    healthy_idx = result.class_order.index("healthy")
    cooling_idx = result.class_order.index("cooling_degradation")
    assert result.confusion_matrix[healthy_idx][healthy_idx] == 3
    assert result.confusion_matrix[cooling_idx][cooling_idx] == 1


def test_class_order_is_fixed_and_complete() -> None:
    y_true = np.array(["healthy"])
    y_pred = np.array(["healthy"])
    result = compute_multiclass_metrics(y_true, y_pred)
    assert result.class_order == PRIMARY_CLASSES
    assert set(result.per_class) == set(PRIMARY_CLASSES)
    assert len(result.confusion_matrix) == len(PRIMARY_CLASSES)
    assert all(len(row) == len(PRIMARY_CLASSES) for row in result.confusion_matrix)
