"""Validation-only hysteresis grid search for the robust candidate (PR175
spec sections 2, 4, 5).

Deliberately a new module, not an edit to `alert_policy/policy_search.py`
— that module's grid and selection rule are PR170's frozen, still-in-use
policy for the *original* system (System A); PR175 evaluates a different
grid with a stricter (zero-tolerance any-fault-miss) rejection rule
against the robust candidate's own validation split, so editing it in
place would silently change System A's own historical selection. Reuses
`ood.gapped_alert_evaluation`'s insufficient-data-aware detection/false-
alert functions unchanged (spec section 3: preserve PR173 semantics) —
this module only supplies the grid and the selection rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.data_loading import InsufficientDataSummary
from backend.simulator.dataset.ood.gapped_alert_evaluation import (
    evaluate_gapped_detection,
    evaluate_gapped_false_alerts,
)
from backend.simulator.dataset.robustness.policy_config import (
    ENTRY_PERSISTENCE_GRID,
    ENTRY_PROBABILITY_GRID,
    EXIT_PERSISTENCE_GRID,
    HEALTHY_EXIT_PROBABILITY_GRID,
    LATENCY_DEGRADATION_TOLERANCE_SECONDS,
    MAX_MISSED_VALIDATION_ANY_FAULT_RUNS,
    MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS,
    SELECTION_RULE_DESCRIPTION,
)


@dataclass(frozen=True)
class RobustPolicyCandidate:
    config: StateMachineConfig
    any_fault_missed_run_count: int
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
            "any_fault_missed_run_count": self.any_fault_missed_run_count,
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
class RobustPolicySearchResult:
    candidates: list[RobustPolicyCandidate]
    selected: RobustPolicyCandidate | None
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
    proba: np.ndarray,
    insufficient_data: InsufficientDataSummary,
    classes: tuple[str, ...],
    config: StateMachineConfig,
    *,
    baseline_median_latency: float | None,
) -> RobustPolicyCandidate:
    detection = evaluate_gapped_detection(
        dataset, proba, insufficient_data, classes, config
    )
    false_alerts = evaluate_gapped_false_alerts(
        dataset, proba, insufficient_data, classes, config
    )

    any_fault_missed = len(detection.any_fault_missed_runs)
    correct_class_missed = len(detection.correct_class_missed_runs)
    total = len(detection.run_results)
    median_latency = detection.median_correct_class_latency_seconds

    rejection_reason: str | None = None
    if any_fault_missed > MAX_MISSED_VALIDATION_ANY_FAULT_RUNS:
        rejection_reason = (
            f"missed {any_fault_missed} of {total} validation fault runs for "
            "any-fault detection (cap is "
            f"{MAX_MISSED_VALIDATION_ANY_FAULT_RUNS})"
        )
    elif correct_class_missed > MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS:
        rejection_reason = (
            f"missed {correct_class_missed} of {total} validation fault runs "
            "for correct-class detection (cap is "
            f"{MAX_MISSED_VALIDATION_CORRECT_CLASS_RUNS})"
        )
    elif (
        baseline_median_latency is not None
        and median_latency is not None
        and median_latency
        > baseline_median_latency + LATENCY_DEGRADATION_TOLERANCE_SECONDS
    ):
        rejection_reason = (
            f"median correct-class latency {median_latency:.0f}s exceeds the "
            f"robust-model-under-PR170-policy baseline {baseline_median_latency:.0f}s "
            f"by more than {LATENCY_DEGRADATION_TOLERANCE_SECONDS:.0f}s"
        )

    return RobustPolicyCandidate(
        config=config,
        any_fault_missed_run_count=any_fault_missed,
        correct_class_missed_run_count=correct_class_missed,
        total_fault_runs=total,
        median_correct_class_latency_seconds=median_latency,
        false_alert_events_per_healthy_hour=(
            false_alerts.false_alert_events_per_healthy_hour
        ),
        healthy_runs_affected=len(false_alerts.healthy_run_ids_with_alert),
        mean_false_episode_duration_seconds=(
            false_alerts.mean_false_episode_duration_seconds
        ),
        rejected=rejection_reason is not None,
        rejection_reason=rejection_reason,
    )


def search_robust_policies(
    dataset: ExperimentDataset,
    proba: np.ndarray,
    insufficient_data: InsufficientDataSummary,
    classes: tuple[str, ...],
    *,
    baseline_median_latency_seconds: float | None,
) -> RobustPolicySearchResult:
    """`dataset`/`proba`/`insufficient_data` must already be narrowed to
    the robust training dataset's validation split (spec section 2) — this
    function has no notion of a split itself, exactly like PR170's own
    `alert_policy.policy_search.search_policies`."""
    candidates: list[RobustPolicyCandidate] = []
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
                            proba,
                            insufficient_data,
                            classes,
                            config,
                            baseline_median_latency=baseline_median_latency_seconds,
                        )
                    )

    survivors = [c for c in candidates if not c.rejected]
    all_rejected = not survivors

    def _sort_key(c: RobustPolicyCandidate) -> tuple[float, int, float, float, int]:
        median = c.median_correct_class_latency_seconds
        return (
            c.false_alert_events_per_healthy_hour,
            c.healthy_runs_affected,
            c.mean_false_episode_duration_seconds,
            median if median is not None else float("inf"),
            c.complexity,
        )

    selected: RobustPolicyCandidate | None = None
    if survivors:
        selected = min(survivors, key=_sort_key)

    return RobustPolicySearchResult(
        candidates=candidates,
        selected=selected,
        baseline_median_latency_seconds=baseline_median_latency_seconds,
        selection_rule=SELECTION_RULE_DESCRIPTION,
        all_rejected=all_rejected,
    )
