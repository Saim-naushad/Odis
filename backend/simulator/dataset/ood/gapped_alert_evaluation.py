"""Insufficient-data-aware alert evaluation (PR173 spec section 6).

`alert_policy.detection.evaluate_detection`/`alert_policy.event_metrics.
compute_false_alert_summary` gather their per-run row sequences from an
already-loaded `ExperimentDataset` + boolean mask — a contract with no
notion of a *rejected* timestamp, because a rejected row was never in the
pilot/PR171/PR172 feature dataset to begin with (there was no
`feature_rejections.parquet` yet). PR173 changes that: a rejected
timestamp is a real gap in an otherwise-contiguous 10-second-cadence
sequence, and the frozen PR170 alert policy must see that gap explicitly
— not silently skip over it — for the documented `insufficient_data`
policy (breaks pending confirmation, does not clear a confirmed alert,
does not advance exit persistence — see `alert_policy.state_machine`'s
module docstring) to mean anything.

This module builds that merged (valid rows + rejected-row placeholders,
in ascending elapsed-time order) sequence per run, then calls
`alert_policy.detection.evaluate_run_detection` (extended by PR173 with
an optional `row_valid` passthrough) and `alert_policy.state_machine.
run_state_machine` + `alert_policy.event_metrics.episodes_from_events`
directly — reusing every existing piece of event/episode logic
unchanged, rather than re-deriving it, because gathering rows from a
mix of a loaded dataset and a separate rejections file is a genuinely
different input contract than `evaluate_detection`/`compute_false_alert_
summary`'s own dataset+mask gathering.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    RunDetectionResult,
    evaluate_run_detection,
)
from backend.simulator.dataset.alert_policy.event_metrics import (
    FalseAlertSummary,
    episodes_from_events,
)
from backend.simulator.dataset.alert_policy.state_machine import (
    StateMachineConfig,
    run_state_machine,
)
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.data_loading import InsufficientDataSummary


@dataclass(frozen=True)
class GappedRow:
    elapsed_sim_seconds: float
    proba: np.ndarray
    valid: bool


def _target_asset_gapped_sequences(
    dataset: ExperimentDataset,
    proba: np.ndarray,
    summary: InsufficientDataSummary,
    n_classes: int,
) -> dict[str, list[GappedRow]]:
    """One merged, elapsed-time-ordered sequence per `simulation_run_id`,
    restricted to that run's own target asset (mirrors `alert_policy.
    detection`/`event_metrics`'s own target-asset-only restriction) —
    valid dataset rows carry their real `proba`; rejected rows carry an
    all-zero placeholder that is never read (`run_state_machine` skips
    `proba` entirely for a row marked invalid)."""
    sequences: dict[str, list[GappedRow]] = {}
    for idx in range(len(dataset.y)):
        run_id = dataset.run_ids[idx]
        metadata = dataset.run_metadata.get(run_id)
        if metadata is None or dataset.asset_ids[idx] != metadata.target_asset_id:
            continue
        sequences.setdefault(run_id, []).append(
            GappedRow(float(dataset.elapsed_sim_seconds[idx]), proba[idx], True)
        )

    dummy_proba = np.zeros(n_classes, dtype=np.float64)
    for row in summary.rejected_rows:
        metadata = dataset.run_metadata.get(row.simulation_run_id)
        if metadata is None or row.asset_id != metadata.target_asset_id:
            continue
        sequences.setdefault(row.simulation_run_id, []).append(
            GappedRow(row.elapsed_sim_seconds, dummy_proba, False)
        )

    for sequence in sequences.values():
        sequence.sort(key=lambda r: r.elapsed_sim_seconds)
    return sequences


def evaluate_gapped_detection(
    dataset: ExperimentDataset,
    proba: np.ndarray,
    summary: InsufficientDataSummary,
    class_order: tuple[str, ...],
    config: StateMachineConfig,
) -> DetectionSummary:
    """`alert_policy.detection.evaluate_detection`, but insufficient-data
    rows genuinely interrupt the state machine rather than being absent
    from it (see module docstring)."""
    sequences = _target_asset_gapped_sequences(
        dataset, proba, summary, len(class_order)
    )
    results: list[RunDetectionResult] = []
    for run_id, metadata in dataset.run_metadata.items():
        if metadata.fault_class is None or metadata.fault_start_sim_seconds is None:
            continue
        rows = sequences.get(run_id)
        if not rows:
            continue
        results.append(
            evaluate_run_detection(
                [r.elapsed_sim_seconds for r in rows],
                np.array([r.proba for r in rows]),
                class_order,
                config,
                simulation_run_id=run_id,
                fault_class=metadata.fault_class,
                fault_start_sim_seconds=metadata.fault_start_sim_seconds,
                row_valid=[r.valid for r in rows],
            )
        )
    sorted_results = sorted(results, key=lambda r: r.simulation_run_id)
    return DetectionSummary(run_results=sorted_results)


def evaluate_gapped_false_alerts(
    dataset: ExperimentDataset,
    proba: np.ndarray,
    summary: InsufficientDataSummary,
    class_order: tuple[str, ...],
    config: StateMachineConfig,
) -> FalseAlertSummary:
    """`alert_policy.event_metrics.compute_false_alert_summary`, but over
    each run's healthy segment *including* any insufficient-data gaps
    within it (see module docstring)."""
    sequences = _target_asset_gapped_sequences(
        dataset, proba, summary, len(class_order)
    )

    episodes = []
    false_row_count = 0
    healthy_seconds = 0.0
    runs_with_alert: set[str] = set()
    segment_count = 0

    for run_id, rows in sequences.items():
        metadata = dataset.run_metadata[run_id]
        if metadata.fault_class is None:
            healthy_rows = rows
        else:
            fault_start = metadata.fault_start_sim_seconds
            healthy_rows = (
                [r for r in rows if r.elapsed_sim_seconds < fault_start]
                if fault_start is not None
                else []
            )
        if not healthy_rows:
            continue
        segment_count += 1

        elapsed = [r.elapsed_sim_seconds for r in healthy_rows]
        row_proba = np.array([r.proba for r in healthy_rows])
        row_valid = [r.valid for r in healthy_rows]
        result = run_state_machine(
            elapsed, row_proba, class_order, config, row_valid=row_valid
        )

        ignored_states = (HEALTHY_LABEL, "insufficient_data")
        false_row_count += sum(
            1 for s in result.row_states if s not in ignored_states
        )
        # Only valid rows represent an actual healthy-hour of scored
        # telemetry; a rejected row was never a "healthy" observation the
        # alert policy could have false-alarmed on.
        healthy_seconds += sum(1 for r in healthy_rows if r.valid) * DT_SECONDS

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
