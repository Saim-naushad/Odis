"""Streams one planned run's samples into open Parquet writers.

Memory is bounded to one run at a time: `export_run` accumulates only the
current run's rows (typically a few thousand for the run sizes this PR
targets), builds one `pa.Table` per table per run, and writes it — it never
holds more than one run's data, and the caller (`generate.generate_dataset`)
never accumulates rows across runs at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    RUNS_SCHEMA,
    TELEMETRY_SCHEMA,
)
from backend.simulator.dataset.run_plan import PlannedRun
from backend.simulator.dataset.runner import iter_samples


@dataclass(frozen=True)
class RunExportResult:
    """The outcome of exporting one planned run — feeds the `runs.parquet` row."""

    planned_run: PlannedRun
    observation_count: int
    ground_truth_row_count: int
    sample_count: int


def export_run(
    planned_run: PlannedRun,
    *,
    telemetry_writer: pq.ParquetWriter,
    ground_truth_writer: pq.ParquetWriter,
) -> RunExportResult:
    """Run `planned_run.run_config` via `iter_samples` and write its rows.

    Row-level `elapsed_sim_seconds` for both tables comes from the
    `SimulationSample` the observations/ground truth were produced in, not
    recomputed from timestamps — one source of truth, matching how
    `runner.iter_samples` itself derives everything from simulated elapsed
    time.
    """
    dataset_id = planned_run.dataset_id
    run_id = planned_run.simulation_run_id

    telemetry_rows: list[dict[str, object]] = []
    ground_truth_rows: list[dict[str, object]] = []
    sample_count = 0

    for sample in iter_samples(planned_run.run_config):
        sample_count += 1
        for observation in sample.observations:
            telemetry_rows.append(
                {
                    "dataset_id": dataset_id,
                    "simulation_run_id": run_id,
                    "observation_id": observation.id,
                    "timestamp": observation.timestamp,
                    "elapsed_sim_seconds": sample.elapsed_sim_seconds,
                    "asset_id": observation.asset_id,
                    "measurement_type": observation.measurement_type.name,
                    "value": observation.value,
                    "unit": observation.unit,
                }
            )
        for record in sample.ground_truth:
            ground_truth_rows.append(
                {
                    "dataset_id": dataset_id,
                    "simulation_run_id": run_id,
                    "timestamp": record.timestamp,
                    "elapsed_sim_seconds": record.elapsed_sim_seconds,
                    "asset_id": record.asset_id,
                    "fault_type": record.fault_type.value,
                    "fault_active": record.fault_active,
                    "fault_severity": record.fault_severity,
                    "seconds_since_fault_start": record.seconds_since_fault_start,
                    "sensor_corruption_type": record.sensor_corruption_type.value,
                }
            )

    telemetry_writer.write_table(
        pa.Table.from_pylist(telemetry_rows, schema=TELEMETRY_SCHEMA)
    )
    ground_truth_writer.write_table(
        pa.Table.from_pylist(ground_truth_rows, schema=GROUND_TRUTH_SCHEMA)
    )

    return RunExportResult(
        planned_run=planned_run,
        observation_count=len(telemetry_rows),
        ground_truth_row_count=len(ground_truth_rows),
        sample_count=sample_count,
    )


def build_runs_table(run_results: tuple[RunExportResult, ...]) -> pa.Table:
    """Build the `runs.parquet` table from completed run export results.

    Every row here has `status == "success"` — a failed run raises out of
    `generate.generate_dataset` before reaching this point rather than
    being recorded as a failed row (see PR164's failure-handling design).
    """
    rows: list[dict[str, object]] = []
    for result in run_results:
        config = result.planned_run.run_config
        operating_conditions = config.operating_conditions
        initial_state = operating_conditions.initial_state_variation
        rows.append(
            {
                "dataset_id": result.planned_run.dataset_id,
                "simulation_run_id": result.planned_run.simulation_run_id,
                "class_label": result.planned_run.class_label,
                "seed": config.seed,
                "target_asset_id": config.target_asset_id,
                "duration_sim_seconds": config.duration_sim_seconds,
                "dt_seconds": config.dt_seconds,
                "run_start_time": config.run_start_time,
                "fault_start_sim_seconds": config.fault_start_sim_seconds,
                "fault_duration_sim_seconds": config.fault_duration_sim_seconds,
                "fault_severity": config.fault_severity,
                "load_baseline_percent": operating_conditions.load_baseline_percent,
                "load_amplitude_percent": operating_conditions.load_amplitude_percent,
                "load_period_seconds": operating_conditions.load_period_seconds,
                "load_phase_radians": operating_conditions.load_phase_radians,
                "initial_load_offset_percent": initial_state.load_offset_percent,
                "initial_stack_temperature_offset_celsius": (
                    initial_state.stack_temperature_offset_celsius
                ),
                "sensor_noise_json": json.dumps(
                    [
                        noise_config.to_json_dict()
                        for noise_config in operating_conditions.sensor_noise
                    ]
                ),
                "observation_count": result.observation_count,
                "ground_truth_row_count": result.ground_truth_row_count,
                "sample_count": result.sample_count,
                "status": "success",
                "error_message": None,
            }
        )
    return pa.Table.from_pylist(rows, schema=RUNS_SCHEMA)
