"""Calibration-quality metrics on known fixtures (PR169 spec section 11,
"Metrics" test group)."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import log_loss

from backend.simulator.dataset.calibration.calibration_metrics import (
    compute_calibration_metrics,
    compute_expected_calibration_error,
    compute_log_loss,
    compute_multiclass_brier,
    confidence_band_summaries,
)

_CLASSES = ("a", "b")


def test_log_loss_matches_sklearn_reference() -> None:
    y_true = np.array(["a", "b", "a", "b"])
    proba = np.array([[0.9, 0.1], [0.2, 0.8], [0.6, 0.4], [0.3, 0.7]])
    expected = log_loss(y_true, proba, labels=list(_CLASSES))
    assert compute_log_loss(y_true, proba, _CLASSES) == pytest.approx(expected)


def test_perfect_predictions_have_zero_loss_and_zero_brier() -> None:
    y_true = np.array(["a", "b"])
    proba = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert compute_log_loss(y_true, proba, _CLASSES) == pytest.approx(0.0, abs=1e-9)
    assert compute_multiclass_brier(y_true, proba, _CLASSES) == pytest.approx(0.0)


def test_multiclass_brier_known_value() -> None:
    # One row: true class "a", predicted [0.7, 0.3].
    # Brier = (0.7-1)^2 + (0.3-0)^2 = 0.09 + 0.09 = 0.18
    y_true = np.array(["a"])
    proba = np.array([[0.7, 0.3]])
    assert compute_multiclass_brier(y_true, proba, _CLASSES) == pytest.approx(0.18)


def test_ece_zero_for_perfectly_calibrated_uniform_confidence() -> None:
    # 10 rows, all predicted confidence 0.8 for the argmax class, and
    # exactly 80% of them are correct -> accuracy matches confidence.
    y_true = np.array(["a"] * 8 + ["b"] * 2)
    proba = np.array([[0.8, 0.2]] * 10)
    ece = compute_expected_calibration_error(y_true, proba, _CLASSES, n_bins=10)
    assert ece == pytest.approx(0.0, abs=1e-9)


def test_ece_positive_when_overconfident() -> None:
    # All predicted at 0.9 confidence but only 50% correct -> large gap.
    y_true = np.array(["a"] * 5 + ["b"] * 5)
    proba = np.array([[0.9, 0.1]] * 10)
    ece = compute_expected_calibration_error(y_true, proba, _CLASSES, n_bins=10)
    assert ece == pytest.approx(0.4, abs=1e-9)


def test_confidence_band_summaries_bucket_rows_correctly() -> None:
    y_true = np.array(["a", "a", "b", "b"])
    proba = np.array([[0.95, 0.05], [0.55, 0.45], [0.95, 0.05], [0.55, 0.45]])
    bands = confidence_band_summaries(y_true, proba, _CLASSES)
    band_names = {b.band for b in bands}
    # 0.95-confidence rows and 0.55-confidence rows fall in different bands.
    assert len(band_names) == 2
    total_rows = sum(b.row_count for b in bands)
    assert total_rows == 4


def test_compute_calibration_metrics_bundles_everything() -> None:
    y_true = np.array(["a", "b", "a", "b"])
    proba = np.array([[0.9, 0.1], [0.2, 0.8], [0.6, 0.4], [0.3, 0.7]])
    metrics = compute_calibration_metrics(y_true, proba, _CLASSES)
    assert metrics.log_loss >= 0.0
    assert metrics.multiclass_brier >= 0.0
    assert 0.0 <= metrics.expected_calibration_error <= 1.0
    assert len(metrics.confidence_bands) > 0
    assert len(metrics.per_class_reliability) == len(_CLASSES)
    assert "mean" in metrics.confidence_distribution
