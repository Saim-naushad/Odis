"""PR168 row-sequence baseline, recomputed under PR170's event/episode
definition for a fair comparison, plus the PR169 historical reference
(spec section 7).

The PR168 baseline is never re-selected here — it is exactly "3
consecutive identical fault predictions" (`config.
COMPARISON_PERSISTENCE_SAMPLES`, PR168's own chosen `N`), reusing
`models.detection.find_first_qualifying_detection` unchanged for
detection latency. Its *false-alert* metrics are recomputed fresh using
the same episode/duration accounting `event_metrics.py` uses for PR170,
because PR168's own report only ever counted persistence-gated events,
not durations — comparing PR168's original number against PR170's
duration-aware one would not be apples-to-apples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.config import COMPARISON_PERSISTENCE_SAMPLES
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.detection import DetectionSummary
from backend.simulator.dataset.models.detection import (
    evaluate_detection as evaluate_row_detection,
)


@dataclass(frozen=True)
class RowSequenceEpisode:
    simulation_run_id: str
    predicted_class: str
    start_elapsed_sim_seconds: float
    end_elapsed_sim_seconds: float
    qualifies_as_event: bool
    """True once the streak reaches `persistence_samples` — mirrors
    PR168's own `count_false_alarm_events`'s "fired" gate."""

    @property
    def duration_seconds(self) -> float:
        return self.end_elapsed_sim_seconds - self.start_elapsed_sim_seconds

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "simulation_run_id": self.simulation_run_id,
            "predicted_class": self.predicted_class,
            "start_elapsed_sim_seconds": self.start_elapsed_sim_seconds,
            "end_elapsed_sim_seconds": self.end_elapsed_sim_seconds,
            "duration_seconds": self.duration_seconds,
            "qualifies_as_event": self.qualifies_as_event,
        }


@dataclass(frozen=True)
class RowSequenceFalseAlertSummary:
    episodes: list[RowSequenceEpisode]
    false_anomalous_row_count: int
    healthy_hours_evaluated: float
    healthy_run_ids_with_alert: set[str]

    @property
    def qualifying_episodes(self) -> list[RowSequenceEpisode]:
        return [e for e in self.episodes if e.qualifies_as_event]

    @property
    def false_confirmed_event_count(self) -> int:
        return len(self.qualifying_episodes)

    @property
    def false_alert_events_per_healthy_hour(self) -> float:
        if self.healthy_hours_evaluated <= 0:
            return 0.0
        return self.false_confirmed_event_count / self.healthy_hours_evaluated

    @property
    def mean_false_episode_duration_seconds(self) -> float:
        durations = [e.duration_seconds for e in self.qualifying_episodes]
        return float(np.mean(durations)) if durations else 0.0

    @property
    def max_false_episode_duration_seconds(self) -> float:
        durations = [e.duration_seconds for e in self.qualifying_episodes]
        return max(durations) if durations else 0.0

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "episodes": [e.to_json_dict() for e in self.episodes],
            "false_confirmed_event_count": self.false_confirmed_event_count,
            "false_anomalous_row_count": self.false_anomalous_row_count,
            "healthy_hours_evaluated": self.healthy_hours_evaluated,
            "false_alert_events_per_healthy_hour": (
                self.false_alert_events_per_healthy_hour
            ),
            "mean_false_episode_duration_seconds": (
                self.mean_false_episode_duration_seconds
            ),
            "max_false_episode_duration_seconds": (
                self.max_false_episode_duration_seconds
            ),
            "healthy_runs_with_alert": len(self.healthy_run_ids_with_alert),
        }


def compute_row_sequence_false_alerts(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    predictions: np.ndarray,
    *,
    persistence_samples: int = COMPARISON_PERSISTENCE_SAMPLES,
) -> RowSequenceFalseAlertSummary:
    indices = np.nonzero(mask)[0]
    rows_by_run: dict[str, list[tuple[float, str]]] = {}
    for position, idx in enumerate(indices):
        run_id = dataset.run_ids[idx]
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or dataset.asset_ids[idx] != metadata.target_asset_id:
            continue
        rows_by_run.setdefault(run_id, []).append(
            (float(dataset.elapsed_sim_seconds[idx]), str(predictions[position]))
        )

    episodes: list[RowSequenceEpisode] = []
    false_row_count = 0
    healthy_seconds = 0.0
    runs_with_alert: set[str] = set()

    for run_id, rows in rows_by_run.items():
        rows.sort(key=lambda pair: pair[0])
        metadata = dataset.run_metadata[run_id]
        if metadata.fault_class is None:
            healthy_rows = rows
        else:
            fault_start = metadata.fault_start_sim_seconds
            if fault_start is None:
                healthy_rows = []
            else:
                healthy_rows = [r for r in rows if r[0] < fault_start]
        if not healthy_rows:
            continue

        healthy_seconds += len(healthy_rows) * DT_SECONDS
        i = 0
        n = len(healthy_rows)
        while i < n:
            cls = healthy_rows[i][1]
            j = i
            while j < n and healthy_rows[j][1] == cls:
                j += 1
            length = j - i
            if cls != HEALTHY_LABEL:
                false_row_count += length
                episode = RowSequenceEpisode(
                    simulation_run_id=run_id,
                    predicted_class=cls,
                    start_elapsed_sim_seconds=healthy_rows[i][0],
                    end_elapsed_sim_seconds=healthy_rows[j - 1][0] + DT_SECONDS,
                    qualifies_as_event=length >= persistence_samples,
                )
                episodes.append(episode)
                if episode.qualifies_as_event:
                    runs_with_alert.add(run_id)
            i = j

    return RowSequenceFalseAlertSummary(
        episodes=episodes,
        false_anomalous_row_count=false_row_count,
        healthy_hours_evaluated=healthy_seconds / 3600.0,
        healthy_run_ids_with_alert=runs_with_alert,
    )


def evaluate_row_sequence_detection(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    predictions: np.ndarray,
    *,
    persistence_samples: int = COMPARISON_PERSISTENCE_SAMPLES,
) -> DetectionSummary:
    """Reuses `models.detection.evaluate_detection` (PR168's own
    correct-class-only detection logic) unchanged."""
    return evaluate_row_detection(
        dataset, mask, predictions, persistence_samples=persistence_samples
    )


def median_latency_seconds(detection: DetectionSummary) -> float | None:
    """`models.detection.DetectionSummary` (PR168's own, reused unchanged
    above) has no median-latency helper of its own — small local
    convenience rather than modifying PR168's module for a PR170-only
    need."""
    latencies = [
        r.latency_seconds
        for r in detection.run_results
        if r.latency_seconds is not None
    ]
    return float(np.median(latencies)) if latencies else None
