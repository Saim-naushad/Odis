"""Validation-only hysteresis grid search and selection (PR170 spec
sections 3 and 6).

Every (entry_probability, entry_persistence, healthy_exit_probability,
exit_persistence) candidate is evaluated and recorded — nothing is
discarded — then `config.SELECTION_RULE_DESCRIPTION`'s four-step rule
picks exactly one. Test-split rows never appear anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.config import (
    ENTRY_PERSISTENCE_GRID,
    ENTRY_PROBABILITY_GRID,
    EXIT_PERSISTENCE_GRID,
    HEALTHY_EXIT_PROBABILITY_GRID,
    LATENCY_DEGRADATION_TOLERANCE_SECONDS,
    MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS,
    SELECTION_RULE_DESCRIPTION,
)
from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    evaluate_detection,
)
from backend.simulator.dataset.alert_policy.event_metrics import (
    FalseAlertSummary,
    compute_false_alert_summary,
)
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset


@dataclass(frozen=True)
class PolicyCandidate:
    config: StateMachineConfig
    correct_class_missed_run_count: int
    total_fault_runs: int
    median_correct_class_latency_seconds: float | None
    false_alert_events_per_healthy_hour: float
    healthy_runs_affected: int
    mean_false_episode_duration_seconds: float
    rejected: bool
    rejection_reason: str | None

    @property
    def complexity(self) -> int:
        return self.config.entry_persistence + self.config.exit_persistence

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_json_dict(),
            "correct_class_missed_run_count": self.correct_class_missed_run_count,
            "total_fault_runs": self.total_fault_runs,
            "median_correct_class_latency_seconds": (
                self.median_correct_class_latency_seconds
            ),
            "false_alert_events_per_healthy_hour": (
                self.false_alert_events_per_healthy_hour
            ),
            "healthy_runs_affected": self.healthy_runs_affected,
            "mean_false_episode_duration_seconds": (
                self.mean_false_episode_duration_seconds
            ),
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class PolicySearchResult:
    candidates: list[PolicyCandidate]
    selected: PolicyCandidate | None
    baseline_median_latency_seconds: float | None
    selection_rule: str
    all_rejected: bool

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "selection_rule": self.selection_rule,
            "baseline_median_latency_seconds": self.baseline_median_latency_seconds,
            "all_rejected": self.all_rejected,
            "candidates": [c.to_json_dict() for c in self.candidates],
            "selected": (
                self.selected.to_json_dict() if self.selected is not None else None
            ),
        }


def _evaluate_candidate(
    dataset: ExperimentDataset,
    val_mask: np.ndarray,
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
    *,
    baseline_median_latency: float | None,
) -> PolicyCandidate:
    detection: DetectionSummary = evaluate_detection(
        dataset, val_mask, proba, classes, config
    )
    false_alerts: FalseAlertSummary = compute_false_alert_summary(
        dataset, val_mask, proba, classes, config
    )

    missed = len(detection.correct_class_missed_runs)
    total = len(detection.run_results)
    median_latency = detection.median_correct_class_latency_seconds

    rejection_reason: str | None = None
    if missed > MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS:
        rejection_reason = (
            f"missed {missed} of {total} validation fault runs for correct-class "
            f"detection (cap is {MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS})"
        )
    elif (
        baseline_median_latency is not None
        and median_latency is not None
        and median_latency
        > baseline_median_latency + LATENCY_DEGRADATION_TOLERANCE_SECONDS
    ):
        rejection_reason = (
            f"median correct-class latency {median_latency:.0f}s exceeds baseline "
            f"{baseline_median_latency:.0f}s by more than "
            f"{LATENCY_DEGRADATION_TOLERANCE_SECONDS:.0f}s"
        )

    return PolicyCandidate(
        config=config,
        correct_class_missed_run_count=missed,
        total_fault_runs=total,
        median_correct_class_latency_seconds=median_latency,
        false_alert_events_per_healthy_hour=false_alerts.false_alert_events_per_healthy_hour,
        healthy_runs_affected=len(false_alerts.healthy_run_ids_with_alert),
        mean_false_episode_duration_seconds=false_alerts.mean_false_episode_duration_seconds,
        rejected=rejection_reason is not None,
        rejection_reason=rejection_reason,
    )


def search_policies(
    dataset: ExperimentDataset,
    val_mask: np.ndarray,
    proba: np.ndarray,
    classes: tuple[str, ...],
    *,
    baseline_median_latency_seconds: float | None,
) -> PolicySearchResult:
    candidates: list[PolicyCandidate] = []
    for entry_probability in ENTRY_PROBABILITY_GRID:
        for entry_persistence in ENTRY_PERSISTENCE_GRID:
            for healthy_exit_probability in HEALTHY_EXIT_PROBABILITY_GRID:
                for exit_persistence in EXIT_PERSISTENCE_GRID:
                    config = StateMachineConfig(
                        entry_probability=entry_probability,
                        entry_persistence=entry_persistence,
                        healthy_exit_probability=healthy_exit_probability,
                        exit_persistence=exit_persistence,
                    )
                    candidates.append(
                        _evaluate_candidate(
                            dataset,
                            val_mask,
                            proba,
                            classes,
                            config,
                            baseline_median_latency=baseline_median_latency_seconds,
                        )
                    )

    survivors = [c for c in candidates if not c.rejected]
    all_rejected = not survivors

    def _sort_key(c: PolicyCandidate) -> tuple[float, int, float, float, int]:
        median = c.median_correct_class_latency_seconds
        return (
            c.false_alert_events_per_healthy_hour,
            c.healthy_runs_affected,
            c.mean_false_episode_duration_seconds,
            median if median is not None else float("inf"),
            c.complexity,
        )

    selected: PolicyCandidate | None = None
    if survivors:
        selected = min(survivors, key=_sort_key)

    return PolicySearchResult(
        candidates=candidates,
        selected=selected,
        baseline_median_latency_seconds=baseline_median_latency_seconds,
        selection_rule=SELECTION_RULE_DESCRIPTION,
        all_rejected=all_rejected,
    )
