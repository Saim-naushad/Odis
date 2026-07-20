"""Run-level fault detection via the alert state machine (PR170 spec
section 5).

Runs the FSM once over each fault run's **entire** target-asset row
sequence (unlike `event_metrics.py`'s healthy-segment-only scan), then
classifies detection from the emitted events: only a `new_alert` or
`class_change` event at or after `fault_start_sim_seconds` counts —
never a state that happened to already be confirmed before onset with no
post-onset transition (spec section 5's "prefer requiring a correct
post-onset transition or correct-class confirmation"). That pre-existing
state is tracked separately as `confirmed_active_at_onset`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    StateMachineConfig,
    run_state_machine,
)
from backend.simulator.dataset.models.config import DETECTION_LATENCY_THRESHOLDS_SECONDS
from backend.simulator.dataset.models.data import ExperimentDataset


@dataclass(frozen=True)
class RunDetectionResult:
    simulation_run_id: str
    fault_class: str
    fault_start_sim_seconds: float
    correct_class_detected: bool
    correct_class_latency_seconds: float | None
    any_fault_detected: bool
    any_fault_latency_seconds: float | None
    any_fault_class_at_first_detection: str | None
    incorrect_class_confirmed_before_correct: bool
    confirmed_active_at_onset: bool
    confirmed_class_at_onset: str | None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "simulation_run_id": self.simulation_run_id,
            "fault_class": self.fault_class,
            "fault_start_sim_seconds": self.fault_start_sim_seconds,
            "correct_class_detected": self.correct_class_detected,
            "correct_class_latency_seconds": self.correct_class_latency_seconds,
            "any_fault_detected": self.any_fault_detected,
            "any_fault_latency_seconds": self.any_fault_latency_seconds,
            "any_fault_class_at_first_detection": (
                self.any_fault_class_at_first_detection
            ),
            "incorrect_class_confirmed_before_correct": (
                self.incorrect_class_confirmed_before_correct
            ),
            "confirmed_active_at_onset": self.confirmed_active_at_onset,
            "confirmed_class_at_onset": self.confirmed_class_at_onset,
        }


def evaluate_run_detection(
    elapsed_sim_seconds: list[float],
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
    *,
    simulation_run_id: str,
    fault_class: str,
    fault_start_sim_seconds: float,
) -> RunDetectionResult:
    result = run_state_machine(elapsed_sim_seconds, proba, classes, config)

    confirmed_class_at_onset: str | None = None
    for event in result.events:
        if event.elapsed_sim_seconds >= fault_start_sim_seconds:
            break
        if event.event_type in ("new_alert", "class_change"):
            confirmed_class_at_onset = event.fault_class
        elif event.event_type == "cleared":
            confirmed_class_at_onset = None

    post_onset_events = [
        e
        for e in result.events
        if e.elapsed_sim_seconds >= fault_start_sim_seconds
        and e.event_type in ("new_alert", "class_change")
    ]
    any_fault_event = post_onset_events[0] if post_onset_events else None
    correct_class_event = next(
        (e for e in post_onset_events if e.fault_class == fault_class), None
    )

    incorrect_before_correct = False
    if any_fault_event is not None and any_fault_event.fault_class != fault_class:
        no_correct_yet = correct_class_event is None
        before_correct = correct_class_event is not None and (
            any_fault_event.elapsed_sim_seconds
            < correct_class_event.elapsed_sim_seconds
        )
        if no_correct_yet or before_correct:
            incorrect_before_correct = True

    return RunDetectionResult(
        simulation_run_id=simulation_run_id,
        fault_class=fault_class,
        fault_start_sim_seconds=fault_start_sim_seconds,
        correct_class_detected=correct_class_event is not None,
        correct_class_latency_seconds=(
            correct_class_event.elapsed_sim_seconds - fault_start_sim_seconds
            if correct_class_event is not None
            else None
        ),
        any_fault_detected=any_fault_event is not None,
        any_fault_latency_seconds=(
            any_fault_event.elapsed_sim_seconds - fault_start_sim_seconds
            if any_fault_event is not None
            else None
        ),
        any_fault_class_at_first_detection=(
            any_fault_event.fault_class if any_fault_event is not None else None
        ),
        incorrect_class_confirmed_before_correct=incorrect_before_correct,
        confirmed_active_at_onset=confirmed_class_at_onset is not None,
        confirmed_class_at_onset=confirmed_class_at_onset,
    )


@dataclass(frozen=True)
class DetectionSummary:
    run_results: list[RunDetectionResult]

    @property
    def correct_class_missed_runs(self) -> list[str]:
        return [
            r.simulation_run_id
            for r in self.run_results
            if not r.correct_class_detected
        ]

    @property
    def any_fault_missed_runs(self) -> list[str]:
        return [
            r.simulation_run_id for r in self.run_results if not r.any_fault_detected
        ]

    @property
    def correct_class_latencies(self) -> list[float]:
        return [
            r.correct_class_latency_seconds
            for r in self.run_results
            if r.correct_class_latency_seconds is not None
        ]

    def detected_within_seconds(self, threshold: float) -> float:
        if not self.run_results:
            return 0.0
        within = sum(
            1
            for r in self.run_results
            if r.correct_class_detected
            and r.correct_class_latency_seconds is not None
            and r.correct_class_latency_seconds <= threshold
        )
        return within / len(self.run_results)

    @property
    def median_correct_class_latency_seconds(self) -> float | None:
        latencies = self.correct_class_latencies
        return float(np.median(latencies)) if latencies else None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "run_results": [r.to_json_dict() for r in self.run_results],
            "correct_class_missed_runs": self.correct_class_missed_runs,
            "any_fault_missed_runs": self.any_fault_missed_runs,
            "median_correct_class_latency_seconds": (
                self.median_correct_class_latency_seconds
            ),
            "detected_within_seconds": {
                str(t): self.detected_within_seconds(t)
                for t in DETECTION_LATENCY_THRESHOLDS_SECONDS
            },
        }


def evaluate_detection(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
) -> DetectionSummary:
    indices = np.nonzero(mask)[0]
    rows_by_run: dict[str, list[tuple[float, np.ndarray]]] = {}
    for position, idx in enumerate(indices):
        run_id = dataset.run_ids[idx]
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or dataset.asset_ids[idx] != metadata.target_asset_id:
            continue
        rows_by_run.setdefault(run_id, []).append(
            (float(dataset.elapsed_sim_seconds[idx]), proba[position])
        )

    results: list[RunDetectionResult] = []
    for run_id, rows in rows_by_run.items():
        metadata = dataset.run_metadata[run_id]
        if metadata.fault_class is None or metadata.fault_start_sim_seconds is None:
            continue
        rows.sort(key=lambda pair: pair[0])
        elapsed = [r[0] for r in rows]
        row_proba = np.array([r[1] for r in rows])
        results.append(
            evaluate_run_detection(
                elapsed,
                row_proba,
                classes,
                config,
                simulation_run_id=run_id,
                fault_class=metadata.fault_class,
                fault_start_sim_seconds=metadata.fault_start_sim_seconds,
            )
        )

    sorted_results = sorted(results, key=lambda r: r.simulation_run_id)
    return DetectionSummary(run_results=sorted_results)
