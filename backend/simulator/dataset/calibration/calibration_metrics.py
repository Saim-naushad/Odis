"""Probability-quality metrics, before vs. after calibration (PR169 spec
section 3).

Every metric here judges the *probabilities themselves* — never
classification accuracy, which calibration is not expected to change
(sigmoid calibration is monotonic per class within scikit-learn's
one-vs-rest scheme, so `argmax` predictions rarely change at all; the
whole point of this module is to prove the probabilities became more
trustworthy even when accuracy stays flat).

**Caveat, stated once here rather than at every call site**: the
validation-split numbers this module computes are evaluated on the same
rows the sigmoid calibrator was fit on (see `calibrate.py`'s module
docstring) — informative for before/after comparison, but not a fully
independent holdout the way the untouched test split is. Every report
that surfaces these numbers must say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import log_loss

_CONFIDENCE_BAND_EDGES: tuple[float, ...] = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 + 1e-9)
_ECE_BINS = 10


def compute_log_loss(
    y_true: np.ndarray, proba: np.ndarray, class_order: tuple[str, ...]
) -> float:
    return float(log_loss(y_true, proba, labels=list(class_order)))


def compute_multiclass_brier(
    y_true: np.ndarray, proba: np.ndarray, class_order: tuple[str, ...]
) -> float:
    """Mean, over rows, of the sum of squared (probability - one_hot)
    differences across every class — the standard one-vs-rest multiclass
    Brier aggregate (equivalent to summing the per-class binary Brier
    scores for one row, then averaging over rows)."""
    one_hot = np.array(
        [[1.0 if c == label else 0.0 for c in class_order] for label in y_true]
    )
    return float(np.mean(np.sum((proba - one_hot) ** 2, axis=1)))


def compute_expected_calibration_error(
    y_true: np.ndarray,
    proba: np.ndarray,
    class_order: tuple[str, ...],
    *,
    n_bins: int = _ECE_BINS,
) -> float:
    """Standard top-label ECE: bin rows by their own predicted-class
    confidence (`max(proba)`), and weight each bin's |accuracy -
    mean-confidence| gap by the bin's row share."""
    predicted_index = proba.argmax(axis=1)
    confidence = proba.max(axis=1)
    predicted_labels = np.array(class_order)[predicted_index]
    correct = (predicted_labels == y_true).astype(np.float64)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(confidence)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (confidence > lo) & (confidence <= hi) if i > 0 else (
            (confidence >= lo) & (confidence <= hi)
        )
        if not mask.any():
            continue
        bin_confidence = confidence[mask].mean()
        bin_accuracy = correct[mask].mean()
        ece += (mask.sum() / n) * abs(bin_accuracy - bin_confidence)
    return float(ece)


@dataclass(frozen=True)
class ConfidenceBandSummary:
    band: str
    row_count: int
    mean_confidence: float
    accuracy: float
    balanced_accuracy: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "row_count": self.row_count,
            "mean_confidence": self.mean_confidence,
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
        }


def _balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Unweighted mean per-class recall — avoided importing
    `sklearn.metrics.balanced_accuracy_score` here to skip its
    zero-division warning noise on tiny per-band slices; a class absent
    from a band contributes no term (matches sklearn's own behavior of
    averaging only over classes present in `y_true`)."""
    recalls = []
    for class_label in sorted(set(y_true)):
        mask = y_true == class_label
        recalls.append((y_pred[mask] == class_label).mean())
    return float(np.mean(recalls)) if recalls else 0.0


def confidence_band_summaries(
    y_true: np.ndarray, proba: np.ndarray, class_order: tuple[str, ...]
) -> list[ConfidenceBandSummary]:
    predicted_index = proba.argmax(axis=1)
    confidence = proba.max(axis=1)
    predicted_labels = np.array(class_order)[predicted_index]

    summaries = []
    for i in range(len(_CONFIDENCE_BAND_EDGES) - 1):
        lo, hi = _CONFIDENCE_BAND_EDGES[i], _CONFIDENCE_BAND_EDGES[i + 1]
        mask = (confidence >= lo) & (confidence < hi)
        if not mask.any():
            continue
        band = f"[{lo:.2f}, {min(hi, 1.0):.2f})" if hi <= 1.0 else f"[{lo:.2f}, 1.00]"
        summaries.append(
            ConfidenceBandSummary(
                band=band,
                row_count=int(mask.sum()),
                mean_confidence=float(confidence[mask].mean()),
                accuracy=float((predicted_labels[mask] == y_true[mask]).mean()),
                balanced_accuracy=_balanced_accuracy(
                    y_true[mask], predicted_labels[mask]
                ),
            )
        )
    return summaries


@dataclass(frozen=True)
class ClassReliability:
    class_label: str
    row_count: int
    mean_predicted_probability: float
    empirical_frequency: float
    """Fraction of rows where this class is actually the true label,
    among rows where it was the *argmax* predicted class — the
    per-class analogue of top-label calibration."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "class_label": self.class_label,
            "row_count": self.row_count,
            "mean_predicted_probability": self.mean_predicted_probability,
            "empirical_frequency": self.empirical_frequency,
        }


def per_class_reliability(
    y_true: np.ndarray, proba: np.ndarray, class_order: tuple[str, ...]
) -> list[ClassReliability]:
    predicted_index = proba.argmax(axis=1)
    confidence = proba.max(axis=1)
    predicted_labels = np.array(class_order)[predicted_index]

    summaries = []
    for class_label in class_order:
        mask = predicted_labels == class_label
        if not mask.any():
            summaries.append(ClassReliability(class_label, 0, 0.0, 0.0))
            continue
        summaries.append(
            ClassReliability(
                class_label=class_label,
                row_count=int(mask.sum()),
                mean_predicted_probability=float(confidence[mask].mean()),
                empirical_frequency=float((y_true[mask] == class_label).mean()),
            )
        )
    return summaries


@dataclass(frozen=True)
class CalibrationMetrics:
    log_loss: float
    multiclass_brier: float
    expected_calibration_error: float
    confidence_bands: list[ConfidenceBandSummary]
    per_class_reliability: list[ClassReliability]
    confidence_distribution: dict[str, float]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "log_loss": self.log_loss,
            "multiclass_brier": self.multiclass_brier,
            "expected_calibration_error": self.expected_calibration_error,
            "confidence_bands": [b.to_json_dict() for b in self.confidence_bands],
            "per_class_reliability": [
                c.to_json_dict() for c in self.per_class_reliability
            ],
            "confidence_distribution": self.confidence_distribution,
        }


def _confidence_distribution(confidence: np.ndarray) -> dict[str, float]:
    quantiles = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
    result = {
        "min": float(confidence.min()),
        "max": float(confidence.max()),
        "mean": float(confidence.mean()),
    }
    for q in quantiles:
        result[f"p{int(q * 100)}"] = float(np.quantile(confidence, q))
    return result


def compute_calibration_metrics(
    y_true: np.ndarray, proba: np.ndarray, class_order: tuple[str, ...]
) -> CalibrationMetrics:
    return CalibrationMetrics(
        log_loss=compute_log_loss(y_true, proba, class_order),
        multiclass_brier=compute_multiclass_brier(y_true, proba, class_order),
        expected_calibration_error=compute_expected_calibration_error(
            y_true, proba, class_order
        ),
        confidence_bands=confidence_band_summaries(y_true, proba, class_order),
        per_class_reliability=per_class_reliability(y_true, proba, class_order),
        confidence_distribution=_confidence_distribution(proba.max(axis=1)),
    )
