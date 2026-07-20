"""Representative-case selection and concise per-row timelines (spec
section 11).

Selection is deterministic (sorted by `simulation_run_id` wherever more
than one run qualifies for a category) — never a random sample. Timelines
carry only telemetry-derived fields already legitimate as evaluation
metadata (true/predicted label, alert state, elapsed time) — no forbidden
metadata is ever exposed as if it were a model input; it is only used
here, post-hoc, for human-readable inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    StateMachineConfig,
    run_state_machine,
)
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.diagnosis_metrics import RowPredictions


@dataclass(frozen=True)
class TimelineRow:
    elapsed_sim_seconds: float
    true_label: str
    predicted_label: str
    predicted_probability: float
    alert_state: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "elapsed_sim_seconds": self.elapsed_sim_seconds,
            "true_label": self.true_label,
            "predicted_label": self.predicted_label,
            "predicted_probability": self.predicted_probability,
            "alert_state": self.alert_state,
        }


@dataclass(frozen=True)
class RepresentativeCase:
    category: str
    simulation_run_id: str
    fault_class: str | None
    rationale: str
    timeline: list[TimelineRow]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "simulation_run_id": self.simulation_run_id,
            "fault_class": self.fault_class,
            "rationale": self.rationale,
            "timeline": [row.to_json_dict() for row in self.timeline],
        }


def _build_timeline(
    dataset: ExperimentDataset,
    predictions: RowPredictions,
    config: StateMachineConfig,
    run_id: str,
) -> list[TimelineRow]:
    metadata = dataset.run_metadata[run_id]
    positions = [
        i
        for i in range(len(dataset.run_ids))
        if dataset.run_ids[i] == run_id
        and dataset.asset_ids[i] == metadata.target_asset_id
    ]
    positions.sort(key=lambda i: dataset.elapsed_sim_seconds[i])
    if not positions:
        return []

    elapsed = [float(dataset.elapsed_sim_seconds[i]) for i in positions]
    proba = predictions.proba[positions]
    sm_result = run_state_machine(elapsed, proba, predictions.classes, config)

    rows: list[TimelineRow] = []
    for position_index, i in enumerate(positions):
        diag_index = int(np.argmax(proba[position_index]))
        rows.append(
            TimelineRow(
                elapsed_sim_seconds=elapsed[position_index],
                true_label=str(dataset.y[i]),
                predicted_label=predictions.classes[diag_index],
                predicted_probability=float(proba[position_index, diag_index]),
                alert_state=sm_result.row_states[position_index],
            )
        )
    return rows


def select_representative_cases(
    dataset: ExperimentDataset,
    predictions: RowPredictions,
    alerts: AlertEvaluationResult,
    config: StateMachineConfig,
) -> list[RepresentativeCase]:
    cases: list[RepresentativeCase] = []

    detected_runs = sorted(
        (r for r in alerts.detection.run_results if r.correct_class_detected),
        key=lambda r: (r.correct_class_latency_seconds, r.simulation_run_id),
    )
    if detected_runs:
        easy = detected_runs[0]
        cases.append(
            RepresentativeCase(
                category="successful_easy_fault",
                simulation_run_id=easy.simulation_run_id,
                fault_class=easy.fault_class,
                rationale=(
                    f"lowest correct-class detection latency among detected OOD "
                    f"runs ({easy.correct_class_latency_seconds:.0f}s)"
                ),
                timeline=_build_timeline(
                    dataset, predictions, config, easy.simulation_run_id
                ),
            )
        )
        delayed = sorted(
            detected_runs,
            key=lambda r: (r.correct_class_latency_seconds, r.simulation_run_id),
            reverse=True,
        )[0]
        if delayed.simulation_run_id != easy.simulation_run_id:
            cases.append(
                RepresentativeCase(
                    category="delayed_detection",
                    simulation_run_id=delayed.simulation_run_id,
                    fault_class=delayed.fault_class,
                    rationale=(
                        f"highest correct-class detection latency among detected "
                        f"OOD runs ({delayed.correct_class_latency_seconds:.0f}s)"
                    ),
                    timeline=_build_timeline(
                        dataset, predictions, config, delayed.simulation_run_id
                    ),
                )
            )

    incorrect_runs = sorted(
        (
            r
            for r in alerts.detection.run_results
            if r.incorrect_class_confirmed_before_correct
        ),
        key=lambda r: r.simulation_run_id,
    )
    if incorrect_runs:
        run = incorrect_runs[0]
        cases.append(
            RepresentativeCase(
                category="incorrect_class_alert",
                simulation_run_id=run.simulation_run_id,
                fault_class=run.fault_class,
                rationale=(
                    f"confirmed {run.any_fault_class_at_first_detection!r} before "
                    f"the correct class {run.fault_class!r}"
                ),
                timeline=_build_timeline(
                    dataset, predictions, config, run.simulation_run_id
                ),
            )
        )

    missed_runs = sorted(alerts.detection.any_fault_missed_runs)
    if missed_runs:
        run_id = missed_runs[0]
        fault_class = dataset.run_metadata[run_id].fault_class
        cases.append(
            RepresentativeCase(
                category="missed_fault",
                simulation_run_id=run_id,
                fault_class=fault_class,
                rationale="no any-fault detection event for the entire OOD run",
                timeline=_build_timeline(dataset, predictions, config, run_id),
            )
        )

    false_alert_runs = sorted(alerts.false_alerts.healthy_run_ids_with_alert)
    if false_alert_runs:
        run_id = false_alert_runs[0]
        cases.append(
            RepresentativeCase(
                category="false_alert_on_healthy_run",
                simulation_run_id=run_id,
                fault_class=None,
                rationale=(
                    "a false confirmed alert episode occurred on a healthy segment"
                ),
                timeline=_build_timeline(dataset, predictions, config, run_id),
            )
        )

    return cases
