"""False-alert event counting on ground-truth-healthy intervals (PR170
spec section 4).

A false alert event is a `healthy/pending -> confirmed` transition
(`state_machine.AlertEvent` with `event_type == "new_alert"`) whose
`elapsed_sim_seconds` falls inside a genuinely healthy interval — either
an entire healthy-scenario run, or the pre-fault portion of a fault run.
Continued confirmed rows (no further event) count as the *same* episode,
never repeated alarms — this falls directly out of the state machine's
own "one event per transition" design; this module only has to select
*which* events are false and summarize their durations, never re-derive
persistence itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    AlertEvent,
    StateMachineConfig,
    run_state_machine,
)
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.models.data import ExperimentDataset


@dataclass(frozen=True)
class FalseEpisode:
    simulation_run_id: str
    fault_class: str
    start_elapsed_sim_seconds: float
    end_elapsed_sim_seconds: float
    """The episode's end is the matching `"cleared"` event's time, or —
    if the healthy segment ends (run boundary / fault onset) before the
    state ever clears — the last in-segment row's elapsed time (a
    right-censored duration, flagged via `censored`)."""
    censored: bool

    @property
    def duration_seconds(self) -> float:
        return self.end_elapsed_sim_seconds - self.start_elapsed_sim_seconds

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "simulation_run_id": self.simulation_run_id,
            "fault_class": self.fault_class,
            "start_elapsed_sim_seconds": self.start_elapsed_sim_seconds,
            "end_elapsed_sim_seconds": self.end_elapsed_sim_seconds,
            "duration_seconds": self.duration_seconds,
            "censored": self.censored,
        }


@dataclass(frozen=True)
class FalseAlertSummary:
    episodes: list[FalseEpisode]
    false_anomalous_row_count: int
    """Row count across every healthy segment whose FSM state is
    `pending_*` or `confirmed_*` (i.e. any row-level departure from
    `healthy`, not just confirmed ones) — the "row noise" figure PR169's
    `false_alarm_rows_by_class` analysis reported."""
    healthy_hours_evaluated: float
    healthy_run_ids_with_alert: set[str]
    total_healthy_run_segments: int

    @property
    def false_confirmed_event_count(self) -> int:
        return len(self.episodes)

    @property
    def false_alert_events_per_healthy_hour(self) -> float:
        if self.healthy_hours_evaluated <= 0:
            return 0.0
        return len(self.episodes) / self.healthy_hours_evaluated

    @property
    def mean_false_episode_duration_seconds(self) -> float:
        if not self.episodes:
            return 0.0
        return float(np.mean([e.duration_seconds for e in self.episodes]))

    @property
    def max_false_episode_duration_seconds(self) -> float:
        if not self.episodes:
            return 0.0
        return max(e.duration_seconds for e in self.episodes)

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
            "total_healthy_run_segments": self.total_healthy_run_segments,
        }


def episodes_from_events(
    run_id: str, events: list[AlertEvent], segment_end_elapsed: float
) -> list[FalseEpisode]:
    episodes: list[FalseEpisode] = []
    open_start: float | None = None
    open_class: str | None = None
    for event in events:
        if event.event_type in ("new_alert",):
            open_start = event.elapsed_sim_seconds
            open_class = event.fault_class
        elif event.event_type == "class_change" and open_start is not None:
            # The episode continues under a new class label — end the
            # first, open a second, both attributed to their own class.
            assert open_class is not None
            episodes.append(
                FalseEpisode(
                    run_id, open_class, open_start, event.elapsed_sim_seconds, False
                )
            )
            open_start = event.elapsed_sim_seconds
            open_class = event.fault_class
        elif event.event_type == "cleared" and open_start is not None:
            assert open_class is not None
            episodes.append(
                FalseEpisode(
                    run_id, open_class, open_start, event.elapsed_sim_seconds, False
                )
            )
            open_start = None
            open_class = None
    if open_start is not None and open_class is not None:
        episodes.append(
            FalseEpisode(run_id, open_class, open_start, segment_end_elapsed, True)
        )
    return episodes


def compute_false_alert_summary(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
) -> FalseAlertSummary:
    """Run the state machine independently over each run's *healthy*
    segment only (the whole run for a healthy-scenario run, or the rows
    before `fault_start_sim_seconds` for a fault run), starting fresh at
    `healthy` each time."""
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

    episodes: list[FalseEpisode] = []
    false_row_count = 0
    healthy_seconds = 0.0
    runs_with_alert: set[str] = set()
    segment_count = 0

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
        segment_count += 1

        elapsed = [r[0] for r in healthy_rows]
        row_proba = np.array([r[1] for r in healthy_rows])
        result = run_state_machine(elapsed, row_proba, classes, config)

        false_row_count += sum(1 for s in result.row_states if s != "healthy")
        healthy_seconds += len(healthy_rows) * DT_SECONDS

        segment_end = elapsed[-1] + DT_SECONDS
        run_episodes = episodes_from_events(run_id, result.events, segment_end)
        if run_episodes:
            runs_with_alert.add(run_id)
        episodes.extend(run_episodes)

    return FalseAlertSummary(
        episodes=episodes,
        false_anomalous_row_count=false_row_count,
        healthy_hours_evaluated=healthy_seconds / 3600.0,
        healthy_run_ids_with_alert=runs_with_alert,
        total_healthy_run_segments=segment_count,
    )
