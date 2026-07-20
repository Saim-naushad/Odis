"""Run-level alert policy over a post-abstention diagnosis stream (PR169
spec section 5).

A qualifying alert requires the same non-healthy, non-`"uncertain"` class
for `persistence_samples` consecutive **non-abstained** samples.
`"uncertain"` is never treated as `"healthy"` and never silently skipped —
it **breaks** the consecutive sequence (the spec's recommended,
conservative first-implementation choice: simple to explain, and it never
lets a low-confidence sample "count toward" an alert).

Reuses `models.detection.find_first_qualifying_detection` unchanged — it
already resets its streak on any non-matching label, and `"uncertain"` is
just another non-matching label, so "breaks the sequence" falls out for
free. False-alarm counting needs its own version here: the PR168
`count_false_alarm_events` only ever excluded `"healthy"` from counting as
an alarm; a persistent `"uncertain"` streak must not count as a false
alarm either (withholding a diagnosis is not the same failure as a
confident wrong one).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.calibration.config import UNCERTAIN_LABEL
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.models.config import (
    DETECTION_LATENCY_THRESHOLDS_SECONDS,
    HEALTHY_LABEL,
)
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.detection import find_first_qualifying_detection

_NON_ALARM_LABELS = frozenset({HEALTHY_LABEL, UNCERTAIN_LABEL})


def count_false_alarm_events(
    diagnoses: Sequence[str], *, persistence_samples: int
) -> int:
    """Same rising-edge-once counting as `models.detection.
    count_false_alarm_events`, but a persistent `"uncertain"` streak is
    excluded from counting as an alarm, exactly like `"healthy"`."""
    count = 0
    streak = 0
    current: str | None = None
    fired = False
    for diagnosis in diagnoses:
        if diagnosis == current:
            streak += 1
        else:
            current = diagnosis
            streak = 1
            fired = False
        qualifies = streak == persistence_samples and current not in _NON_ALARM_LABELS
        if qualifies and not fired:
            count += 1
            fired = True
    return count


@dataclass(frozen=True)
class AlertRunResult:
    simulation_run_id: str
    fault_class: str
    fault_start_sim_seconds: float
    detected: bool
    latency_seconds: float | None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "simulation_run_id": self.simulation_run_id,
            "fault_class": self.fault_class,
            "fault_start_sim_seconds": self.fault_start_sim_seconds,
            "detected": self.detected,
            "latency_seconds": self.latency_seconds,
        }


@dataclass(frozen=True)
class AlertPolicySummary:
    confidence_threshold: float
    persistence_samples: int
    run_results: list[AlertRunResult]
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

    @property
    def latencies(self) -> list[float]:
        return [
            r.latency_seconds for r in self.run_results if r.latency_seconds is not None
        ]

    def detected_within_seconds(self, threshold: float) -> float:
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

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "persistence_samples": self.persistence_samples,
            "run_results": [r.to_json_dict() for r in self.run_results],
            "false_alarm_event_count": self.false_alarm_event_count,
            "healthy_hours_evaluated": self.healthy_hours_evaluated,
            "false_alarms_per_healthy_hour": self.false_alarms_per_healthy_hour,
            "missed_runs": self.missed_runs,
            "median_latency_seconds": (
                float(np.median(self.latencies)) if self.latencies else None
            ),
            "max_latency_seconds": max(self.latencies) if self.latencies else None,
            "detected_within_seconds": {
                str(t): self.detected_within_seconds(t)
                for t in DETECTION_LATENCY_THRESHOLDS_SECONDS
            },
        }


def evaluate_alert_policy(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    diagnosis: np.ndarray,
    *,
    confidence_threshold: float,
    persistence_samples: int,
) -> AlertPolicySummary:
    """Evaluate one (confidence_threshold, persistence_samples) alert
    policy over the rows selected by `mask`, with `diagnosis` (already
    computed via `abstention.diagnose`) aligned 1:1 to `dataset.X[mask]`
    in that same row order."""
    indices = np.nonzero(mask)[0]
    rows_by_run: dict[str, list[tuple[float, str]]] = {}
    for position, idx in enumerate(indices):
        run_id = dataset.run_ids[idx]
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or dataset.asset_ids[idx] != metadata.target_asset_id:
            continue
        rows_by_run.setdefault(run_id, []).append(
            (float(dataset.elapsed_sim_seconds[idx]), str(diagnosis[position]))
        )

    run_results: list[AlertRunResult] = []
    false_alarm_events = 0
    healthy_seconds = 0.0

    for run_id, rows in rows_by_run.items():
        rows.sort(key=lambda pair: pair[0])
        elapsed = [e for e, _d in rows]
        diagnoses = [d for _e, d in rows]
        metadata = dataset.run_metadata[run_id]
        fault_class = metadata.fault_class

        if fault_class is None:
            false_alarm_events += count_false_alarm_events(
                diagnoses, persistence_samples=persistence_samples
            )
            healthy_seconds += len(diagnoses) * DT_SECONDS
            continue

        fault_start = metadata.fault_start_sim_seconds
        if fault_start is None:
            continue

        pre_fault_diagnoses = [d for e, d in rows if e < fault_start]
        false_alarm_events += count_false_alarm_events(
            pre_fault_diagnoses, persistence_samples=persistence_samples
        )
        healthy_seconds += len(pre_fault_diagnoses) * DT_SECONDS

        first_detection = find_first_qualifying_detection(
            elapsed,
            diagnoses,
            target_class=fault_class,
            fault_start_sim_seconds=fault_start,
            persistence_samples=persistence_samples,
        )
        latency = None if first_detection is None else first_detection - fault_start
        run_results.append(
            AlertRunResult(
                simulation_run_id=run_id,
                fault_class=fault_class,
                fault_start_sim_seconds=fault_start,
                detected=first_detection is not None,
                latency_seconds=latency,
            )
        )

    return AlertPolicySummary(
        confidence_threshold=confidence_threshold,
        persistence_samples=persistence_samples,
        run_results=sorted(run_results, key=lambda r: r.simulation_run_id),
        false_alarm_event_count=false_alarm_events,
        healthy_hours_evaluated=healthy_seconds / 3600.0,
    )
