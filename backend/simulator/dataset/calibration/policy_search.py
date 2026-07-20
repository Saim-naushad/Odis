"""Validation-only (threshold x persistence) policy search and selection
(PR169 spec sections 5 and 6).

Every candidate combination is evaluated and recorded — nothing is
discarded — then `config.SELECTION_RULE_DESCRIPTION`'s three-step rule
picks exactly one: reject candidates exceeding the missed-run cap,
minimize false alarms per healthy hour among survivors, tie-break by
median latency then coverage. Test-split rows never appear anywhere in
this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.calibration.abstention import (
    compute_coverage_metrics,
    diagnose,
)
from backend.simulator.dataset.calibration.alert_policy import (
    AlertPolicySummary,
    evaluate_alert_policy,
)
from backend.simulator.dataset.calibration.config import (
    CONFIDENCE_THRESHOLD_GRID,
    MAX_MISSED_VALIDATION_FAULT_RUNS,
    PERSISTENCE_GRID,
    SELECTION_RULE_DESCRIPTION,
)
from backend.simulator.dataset.models.data import ExperimentDataset


@dataclass(frozen=True)
class PolicyCandidate:
    confidence_threshold: float
    persistence_samples: int
    missed_run_count: int
    total_fault_runs: int
    false_alarms_per_healthy_hour: float
    median_latency_seconds: float | None
    coverage: float
    rejected: bool
    rejection_reason: str | None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "persistence_samples": self.persistence_samples,
            "missed_run_count": self.missed_run_count,
            "total_fault_runs": self.total_fault_runs,
            "false_alarms_per_healthy_hour": self.false_alarms_per_healthy_hour,
            "median_latency_seconds": self.median_latency_seconds,
            "coverage": self.coverage,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class PolicySearchResult:
    candidates: list[PolicyCandidate]
    selected: PolicyCandidate
    selection_rule: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "selection_rule": self.selection_rule,
            "candidates": [c.to_json_dict() for c in self.candidates],
            "selected": self.selected.to_json_dict(),
        }


def _median_latency(summary: AlertPolicySummary) -> float | None:
    return float(np.median(summary.latencies)) if summary.latencies else None


def search_policies(
    dataset: ExperimentDataset,
    val_mask: np.ndarray,
    proba: np.ndarray,
    class_order: tuple[str, ...],
) -> PolicySearchResult:
    y_val = dataset.y[val_mask]
    candidates: list[PolicyCandidate] = []

    for threshold in CONFIDENCE_THRESHOLD_GRID:
        diagnosis = diagnose(proba, class_order, confidence_threshold=threshold)
        coverage_metrics = compute_coverage_metrics(
            y_val, diagnosis, confidence_threshold=threshold
        )
        for persistence in PERSISTENCE_GRID:
            summary = evaluate_alert_policy(
                dataset,
                val_mask,
                diagnosis,
                confidence_threshold=threshold,
                persistence_samples=persistence,
            )
            missed = len(summary.missed_runs)
            total_fault_runs = len(summary.run_results)
            rejected = missed > MAX_MISSED_VALIDATION_FAULT_RUNS
            candidates.append(
                PolicyCandidate(
                    confidence_threshold=threshold,
                    persistence_samples=persistence,
                    missed_run_count=missed,
                    total_fault_runs=total_fault_runs,
                    false_alarms_per_healthy_hour=summary.false_alarms_per_healthy_hour,
                    median_latency_seconds=_median_latency(summary),
                    coverage=coverage_metrics.coverage,
                    rejected=rejected,
                    rejection_reason=(
                        f"missed {missed} of {total_fault_runs} validation fault runs "
                        f"(cap is {MAX_MISSED_VALIDATION_FAULT_RUNS})"
                        if rejected
                        else None
                    ),
                )
            )

    survivors = [c for c in candidates if not c.rejected]
    pool = survivors if survivors else candidates

    def _sort_key(c: PolicyCandidate) -> tuple[float, float, float]:
        median_latency = c.median_latency_seconds
        latency = median_latency if median_latency is not None else math.inf
        return (c.false_alarms_per_healthy_hour, latency, -c.coverage)

    selected = min(pool, key=_sort_key)

    return PolicySearchResult(
        candidates=candidates,
        selected=selected,
        selection_rule=SELECTION_RULE_DESCRIPTION,
    )
