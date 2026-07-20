"""Row-level and run-level uncertainty breakdown (PR169 spec section 7).

Answers, per operating phase/severity/class: does the model abstain
mostly on genuinely difficult mild/ramp samples, or unpredictably on
severe faults; is cooling_degradation disproportionately uncertain; does
calibration change class-confidence ranking? Configured severity is read
purely as evaluation-grouping metadata (via `models.severity.band_for`),
never as a model input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.calibration.config import UNCERTAIN_LABEL
from backend.simulator.dataset.models.config import FAULT_CLASSES, HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.severity import (
    ramp_row_labels,
    severity_band_row_labels,
)


@dataclass(frozen=True)
class UncertaintyGroup:
    group: str
    row_count: int
    uncertain_rate: float
    mean_confidence: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "row_count": self.row_count,
            "uncertain_rate": self.uncertain_rate,
            "mean_confidence": self.mean_confidence,
        }


def _group_summary(
    group_name: str, diagnosis: np.ndarray, confidence: np.ndarray, mask: np.ndarray
) -> UncertaintyGroup | None:
    if not mask.any():
        return None
    return UncertaintyGroup(
        group=group_name,
        row_count=int(mask.sum()),
        uncertain_rate=float((diagnosis[mask] == UNCERTAIN_LABEL).mean()),
        mean_confidence=float(confidence[mask].mean()),
    )


@dataclass(frozen=True)
class UncertaintyReport:
    healthy_vs_fault: list[UncertaintyGroup]
    ramp_vs_post_ramp: list[UncertaintyGroup]
    severity_band: list[UncertaintyGroup]
    per_fault_class: list[UncertaintyGroup]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "healthy_vs_fault": [g.to_json_dict() for g in self.healthy_vs_fault],
            "ramp_vs_post_ramp": [g.to_json_dict() for g in self.ramp_vs_post_ramp],
            "severity_band": [g.to_json_dict() for g in self.severity_band],
            "per_fault_class": [g.to_json_dict() for g in self.per_fault_class],
        }


def compute_uncertainty_report(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    diagnosis: np.ndarray,
    confidence: np.ndarray,
) -> UncertaintyReport:
    y_true = dataset.y[mask]

    healthy_mask = y_true == HEALTHY_LABEL
    fault_mask = ~healthy_mask
    healthy_vs_fault = [
        g
        for g in (
            _group_summary(HEALTHY_LABEL, diagnosis, confidence, healthy_mask),
            _group_summary("active_fault", diagnosis, confidence, fault_mask),
        )
        if g is not None
    ]

    ramp_labels = ramp_row_labels(dataset)[mask]
    ramp_group = _group_summary("ramp", diagnosis, confidence, ramp_labels == "ramp")
    post_ramp_group = _group_summary(
        "post_ramp", diagnosis, confidence, ramp_labels == "post_ramp"
    )
    ramp_vs_post_ramp = [g for g in (ramp_group, post_ramp_group) if g is not None]

    severity_labels = severity_band_row_labels(dataset)[mask]
    severity_band = [
        g
        for band in ("mild", "moderate", "severe")
        if (g := _group_summary(band, diagnosis, confidence, severity_labels == band))
        is not None
    ]

    per_fault_class = [
        g
        for class_label in FAULT_CLASSES
        if (
            g := _group_summary(
                class_label, diagnosis, confidence, y_true == class_label
            )
        )
        is not None
    ]

    return UncertaintyReport(
        healthy_vs_fault=healthy_vs_fault,
        ramp_vs_post_ramp=ramp_vs_post_ramp,
        severity_band=severity_band,
        per_fault_class=per_fault_class,
    )


@dataclass(frozen=True)
class ConfidenceRankingShift:
    class_order_by_mean_confidence_before: tuple[str, ...]
    class_order_by_mean_confidence_after: tuple[str, ...]
    ranking_changed: bool
    mean_confidence_before: dict[str, float]
    mean_confidence_after: dict[str, float]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "class_order_by_mean_confidence_before": list(
                self.class_order_by_mean_confidence_before
            ),
            "class_order_by_mean_confidence_after": list(
                self.class_order_by_mean_confidence_after
            ),
            "ranking_changed": self.ranking_changed,
            "mean_confidence_before": self.mean_confidence_before,
            "mean_confidence_after": self.mean_confidence_after,
        }


def compute_confidence_ranking_shift(
    proba_before: np.ndarray,
    proba_after: np.ndarray,
    class_order: tuple[str, ...],
) -> ConfidenceRankingShift:
    """Per class, the mean predicted probability *for that class's own
    column* (not conditioned on it being the argmax) — a simple, direct
    way to ask "did calibration reorder which classes the model is most
    confident about overall?"."""
    mean_before = {
        c: float(proba_before[:, i].mean()) for i, c in enumerate(class_order)
    }
    mean_after = {c: float(proba_after[:, i].mean()) for i, c in enumerate(class_order)}
    order_before = tuple(
        sorted(class_order, key=lambda c: mean_before[c], reverse=True)
    )
    order_after = tuple(sorted(class_order, key=lambda c: mean_after[c], reverse=True))
    return ConfidenceRankingShift(
        class_order_by_mean_confidence_before=order_before,
        class_order_by_mean_confidence_after=order_after,
        ranking_changed=order_before != order_after,
        mean_confidence_before=mean_before,
        mean_confidence_after=mean_after,
    )
