"""Abstention thresholding and coverage metrics (PR169 spec section 11,
"Abstention" test group)."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.calibration.abstention import (
    compute_coverage_metrics,
    diagnose,
)
from backend.simulator.dataset.calibration.config import UNCERTAIN_LABEL
from backend.simulator.dataset.models.config import HEALTHY_LABEL

_CLASSES = ("cooling_degradation", "healthy", "hydrogen_supply_issue", "sensor_anomaly")


def test_below_threshold_prediction_becomes_uncertain() -> None:
    proba = np.array([[0.4, 0.3, 0.2, 0.1]])
    diagnosis = diagnose(proba, _CLASSES, confidence_threshold=0.5)
    assert diagnosis[0] == UNCERTAIN_LABEL


def test_above_threshold_prediction_retains_its_class() -> None:
    proba = np.array([[0.7, 0.1, 0.1, 0.1]])
    diagnosis = diagnose(proba, _CLASSES, confidence_threshold=0.5)
    assert diagnosis[0] == "cooling_degradation"


def test_exact_threshold_boundary_is_inclusive() -> None:
    proba = np.array([[0.5, 0.3, 0.1, 0.1]])
    diagnosis = diagnose(proba, _CLASSES, confidence_threshold=0.5)
    assert diagnosis[0] == "cooling_degradation"


def test_uncertainty_is_distinct_from_healthy() -> None:
    proba = np.array([[0.3, 0.3, 0.2, 0.2]])  # no class reaches 0.5
    diagnosis = diagnose(proba, _CLASSES, confidence_threshold=0.5)
    assert diagnosis[0] == UNCERTAIN_LABEL
    assert diagnosis[0] != HEALTHY_LABEL


def test_coverage_metrics_per_class_retained_coverage() -> None:
    y_true = np.array(
        [HEALTHY_LABEL, HEALTHY_LABEL, "cooling_degradation", "cooling_degradation"]
    )
    diagnosis = np.array(
        [HEALTHY_LABEL, UNCERTAIN_LABEL, "cooling_degradation", UNCERTAIN_LABEL],
        dtype=object,
    )
    metrics = compute_coverage_metrics(y_true, diagnosis, confidence_threshold=0.5)
    assert metrics.coverage == 0.5
    assert metrics.per_class_retained_coverage[HEALTHY_LABEL] == 0.5
    assert metrics.per_class_retained_coverage["cooling_degradation"] == 0.5


def test_coverage_metrics_healthy_false_positive_excludes_uncertain() -> None:
    y_true = np.array([HEALTHY_LABEL] * 4)
    diagnosis = np.array(
        [HEALTHY_LABEL, "cooling_degradation", UNCERTAIN_LABEL, HEALTHY_LABEL],
        dtype=object,
    )
    metrics = compute_coverage_metrics(y_true, diagnosis, confidence_threshold=0.5)
    # 1 of 4 healthy rows misdiagnosed as a specific wrong class -> FP rate 0.25
    assert metrics.healthy_false_positive_rate == 0.25
    # 1 of 4 healthy rows abstained -> uncertain rate 0.25 (distinct from FP rate)
    assert metrics.uncertain_rate_healthy == 0.25


def test_coverage_metrics_uncertain_rate_active_fault() -> None:
    y_true = np.array(["cooling_degradation", "cooling_degradation", HEALTHY_LABEL])
    diagnosis = np.array(
        ["cooling_degradation", UNCERTAIN_LABEL, HEALTHY_LABEL], dtype=object
    )
    metrics = compute_coverage_metrics(y_true, diagnosis, confidence_threshold=0.5)
    assert metrics.uncertain_rate_active_fault == 0.5


def test_full_coverage_gives_selective_metrics_equal_to_full_metrics() -> None:
    y_true = np.array([HEALTHY_LABEL, "cooling_degradation", HEALTHY_LABEL])
    diagnosis = np.array(
        [HEALTHY_LABEL, "cooling_degradation", HEALTHY_LABEL], dtype=object
    )
    metrics = compute_coverage_metrics(y_true, diagnosis, confidence_threshold=0.5)
    assert metrics.coverage == 1.0
    assert metrics.selective_balanced_accuracy == 1.0
