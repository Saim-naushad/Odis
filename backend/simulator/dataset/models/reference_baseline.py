"""Optional deterministic single-feature threshold reference (PR168 spec
section 10).

Not a third model, and not compared against the two required classifiers
on equal footing — a fixed, training-split-only-fit binary
(healthy-vs-anomalous) threshold rule over Group A's raw measurements,
reported purely as the same kind of descriptive reference point the PR166
audit's `audit/separability.py` already produces, now fit on the training
split and evaluated once on validation and test (never re-fit on either).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.simulator.dataset.models.feature_groups import group_a_columns


@dataclass(frozen=True)
class ThresholdRule:
    measurement: str
    threshold: float
    fault_side: str
    """`"above"` if values >= threshold are called anomalous, `"below"`
    otherwise."""
    train_balanced_accuracy: float

    def predict(self, values: np.ndarray) -> np.ndarray:
        is_anomalous = values >= self.threshold
        if self.fault_side == "below":
            is_anomalous = ~is_anomalous
        return is_anomalous


def _best_threshold_for_measurement(
    values: np.ndarray, is_anomalous: np.ndarray
) -> tuple[float, str, float]:
    """Best split point and direction by balanced accuracy, train-only.

    Same left-to-right sweep-over-sorted-values technique as
    `audit/separability.py`'s `_best_threshold_balanced_accuracy`, adapted
    to also return the winning threshold and direction (the audit module
    only ever needed the accuracy score itself).
    """
    n_fault = int(is_anomalous.sum())
    n_healthy = len(values) - n_fault
    if n_fault == 0 or n_healthy == 0 or len(values) < 2:
        return float(np.median(values)), "above", 0.5

    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    sorted_fault = is_anomalous[order]

    fault_remaining = n_fault
    healthy_seen = 0
    best_balanced = 0.5
    best_threshold = float(sorted_values[0])
    best_direction = "above"

    index = 0
    total = len(sorted_values)
    while index < total:
        value = sorted_values[index]
        while index < total and sorted_values[index] == value:
            if sorted_fault[index]:
                fault_remaining -= 1
            else:
                healthy_seen += 1
            index += 1
        if index < total:
            next_value = float(sorted_values[index])
            balanced_above = 0.5 * (
                fault_remaining / n_fault + healthy_seen / n_healthy
            )
            balanced_below = 1.0 - balanced_above
            if balanced_above > best_balanced:
                best_balanced, best_threshold, best_direction = (
                    balanced_above,
                    next_value,
                    "above",
                )
            if balanced_below > best_balanced:
                best_balanced, best_threshold, best_direction = (
                    balanced_below,
                    next_value,
                    "below",
                )
    return best_threshold, best_direction, best_balanced


def select_reference_threshold_rule(
    x_train_group_a: np.ndarray, y_train_is_anomalous: np.ndarray
) -> ThresholdRule:
    """Sweep every Group A measurement's best single threshold on the
    training split only, and keep the single best-performing one."""
    columns = group_a_columns()
    best: ThresholdRule | None = None
    for i, measurement in enumerate(columns):
        threshold, direction, balanced_accuracy = _best_threshold_for_measurement(
            x_train_group_a[:, i], y_train_is_anomalous
        )
        if best is None or balanced_accuracy > best.train_balanced_accuracy:
            best = ThresholdRule(
                measurement=measurement,
                threshold=threshold,
                fault_side=direction,
                train_balanced_accuracy=balanced_accuracy,
            )
    assert best is not None
    return best


def evaluate_reference_rule(
    rule: ThresholdRule, x_group_a: np.ndarray, y_is_anomalous: np.ndarray
) -> float:
    """Balanced accuracy of the fixed rule against `y_is_anomalous`
    (healthy-vs-anomalous only — this reference is not a multiclass
    classifier)."""
    columns = group_a_columns()
    column_index = columns.index(rule.measurement)
    predicted = rule.predict(x_group_a[:, column_index])
    n_fault = int(y_is_anomalous.sum())
    n_healthy = len(y_is_anomalous) - n_fault
    if n_fault == 0 or n_healthy == 0:
        return 0.5
    true_positive_rate = float((predicted & y_is_anomalous).sum() / n_fault)
    true_negative_rate = float((~predicted & ~y_is_anomalous).sum() / n_healthy)
    return 0.5 * (true_positive_rate + true_negative_rate)
