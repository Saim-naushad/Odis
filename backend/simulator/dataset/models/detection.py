"""Row-level predictions to run-level detection events (PR168 spec section 8).

A single anomalous row never counts as a detected fault. The policy: the
correct fault class must be predicted for `persistence_samples` consecutive
samples (default 3, i.e. 30s at the pilot's 10s cadence) before a run
counts as detected; detection latency is the elapsed time from the
configured fault start to the first sample completing such a streak.
Streaks that start before the fault window opens do not count (spec
section 13's "no detection before fault start counts" case) — this module
resets the streak counter at every sample with
`elapsed_sim_seconds < fault_start_sim_seconds`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.models.config import (
    DETECTION_LATENCY_THRESHOLDS_SECONDS,
    HEALTHY_LABEL,
)
from backend.simulator.dataset.models.data import ExperimentDataset, RunMetadata


def find_first_qualifying_detection(
    elapsed_sim_seconds: Sequence[float],
    predicted_labels: Sequence[str],
    *,
    target_class: str,
    fault_start_sim_seconds: float,
    persistence_samples: int,
) -> float | None:
    """First `elapsed_sim_seconds` at which `target_class` has been
    predicted for `persistence_samples` consecutive samples, restricted to
    samples at or after `fault_start_sim_seconds`. `None` if no such streak
    occurs (a missed run)."""
    streak = 0
    for t, pred in zip(elapsed_sim_seconds, predicted_labels, strict=True):
        if t < fault_start_sim_seconds:
            streak = 0
            continue
        streak = streak + 1 if pred == target_class else 0
        if streak >= persistence_samples:
            return t
    return None


def count_false_alarm_events(
    predicted_labels: Sequence[str], *, persistence_samples: int
) -> int:
    """Count rising-edge qualifying non-healthy persistent streaks within a
    stream the caller has already restricted to a genuinely healthy
    segment. A streak only counts once, at the sample where it first
    reaches `persistence_samples` — a single long false-alarm streak is one
    event, not one per sample past the threshold."""
    count = 0
    streak = 0
    current: str | None = None
    fired = False
    for pred in predicted_labels:
        if pred == current:
            streak += 1
        else:
            current = pred
            streak = 1
            fired = False
        if streak == persistence_samples and current != HEALTHY_LABEL and not fired:
            count += 1
            fired = True
    return count


@dataclass(frozen=True)
class RunDetectionResult:
    simulation_run_id: str
    fault_class: str
    fault_start_sim_seconds: float
    detected: bool
    latency_seconds: float | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "simulation_run_id": self.simulation_run_id,
            "fault_class": self.fault_class,
            "fault_start_sim_seconds": self.fault_start_sim_seconds,
            "detected": self.detected,
            "latency_seconds": self.latency_seconds,
        }


@dataclass(frozen=True)
class DetectionSummary:
    persistence_samples: int
    run_results: list[RunDetectionResult]
    false_alarm_event_count: int
    healthy_hours_evaluated: float

    @property
    def false_alarms_per_healthy_hour(self) -> float:
        if self.healthy_hours_evaluated <= 0:
            return 0.0
        return self.false_alarm_event_count / self.healthy_hours_evaluated

    @property
    def missed_runs(self) -> list[str]:
        return [r.simulation_run_id for r in self.run_results if not r.detected]

    def detected_within_seconds(self, threshold: float) -> float:
        """Fraction of *all evaluated fault runs* (not just detected ones)
        whose latency is within `threshold` seconds."""
        if not self.run_results:
            return 0.0
        within = sum(
            1
            for r in self.run_results
            if r.detected
            and r.latency_seconds is not None
            and r.latency_seconds <= threshold
        )
        return within / len(self.run_results)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "persistence_samples": self.persistence_samples,
            "run_results": [r.to_json_dict() for r in self.run_results],
            "false_alarm_event_count": self.false_alarm_event_count,
            "healthy_hours_evaluated": self.healthy_hours_evaluated,
            "false_alarms_per_healthy_hour": self.false_alarms_per_healthy_hour,
            "missed_runs": self.missed_runs,
            "detected_within_seconds": {
                str(t): self.detected_within_seconds(t)
                for t in DETECTION_LATENCY_THRESHOLDS_SECONDS
            },
        }


def evaluate_detection(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    predictions: np.ndarray,
    *,
    persistence_samples: int,
) -> DetectionSummary:
    """Evaluate the run-level detection-event policy over the rows selected
    by `mask` (e.g. `dataset.split == "test"`), with `predictions` aligned
    1:1 to `dataset.X[mask]` in that same row order."""
    indices = np.nonzero(mask)[0]
    rows_by_run: dict[str, list[tuple[float, str]]] = {}
    for position, idx in enumerate(indices):
        run_id = dataset.run_ids[idx]
        metadata: RunMetadata | None = dataset.run_metadata.get(run_id)
        if metadata is None or dataset.asset_ids[idx] != metadata.target_asset_id:
            continue
        rows_by_run.setdefault(run_id, []).append(
            (
                float(dataset.elapsed_sim_seconds[idx]),
                str(predictions[position]),
            )
        )

    run_results: list[RunDetectionResult] = []
    false_alarm_events = 0
    healthy_seconds = 0.0

    for run_id, rows in rows_by_run.items():
        rows.sort(key=lambda pair: pair[0])
        elapsed = [e for e, _p in rows]
        preds = [p for _e, p in rows]
        metadata = dataset.run_metadata[run_id]
        fault_class = metadata.fault_class

        if fault_class is None:
            false_alarm_events += count_false_alarm_events(
                preds, persistence_samples=persistence_samples
            )
            healthy_seconds += len(preds) * DT_SECONDS
            continue

        fault_start = metadata.fault_start_sim_seconds
        if fault_start is None:
            continue

        pre_fault_preds = [p for e, p in rows if e < fault_start]
        false_alarm_events += count_false_alarm_events(
            pre_fault_preds, persistence_samples=persistence_samples
        )
        healthy_seconds += len(pre_fault_preds) * DT_SECONDS

        first_detection = find_first_qualifying_detection(
            elapsed,
            preds,
            target_class=fault_class,
            fault_start_sim_seconds=fault_start,
            persistence_samples=persistence_samples,
        )
        latency = None if first_detection is None else first_detection - fault_start
        run_results.append(
            RunDetectionResult(
                simulation_run_id=run_id,
                fault_class=fault_class,
                fault_start_sim_seconds=fault_start,
                detected=first_detection is not None,
                latency_seconds=latency,
            )
        )

    return DetectionSummary(
        persistence_samples=persistence_samples,
        run_results=sorted(run_results, key=lambda r: r.simulation_run_id),
        false_alarm_event_count=false_alarm_events,
        healthy_hours_evaluated=healthy_seconds / 3600.0,
    )
