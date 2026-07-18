"""Streaming per-run Parquet export specifications."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
from backend.simulator.dataset.export import (
    RunExportResult,
    build_runs_table,
    export_run,
)
from backend.simulator.dataset.ground_truth import GroundTruthRecord
from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    TELEMETRY_SCHEMA,
)
from backend.simulator.dataset.run_config import DatasetScenario
from backend.simulator.dataset.run_plan import PlannedRun, plan_runs
from backend.simulator.dataset.runner import iter_samples
from domain.entities.observation import Observation

from .conftest import SpecFactory


def _export_single_run(
    tmp_path: Path, planned_run: PlannedRun
) -> tuple[RunExportResult, Path, Path]:
    telemetry_path = tmp_path / "telemetry.parquet"
    ground_truth_path = tmp_path / "ground_truth.parquet"
    with (
        pq.ParquetWriter(telemetry_path, TELEMETRY_SCHEMA) as telemetry_writer,
        pq.ParquetWriter(ground_truth_path, GROUND_TRUTH_SCHEMA) as ground_truth_writer,
    ):
        result = export_run(
            planned_run,
            telemetry_writer=telemetry_writer,
            ground_truth_writer=ground_truth_writer,
        )
    return result, telemetry_path, ground_truth_path


def test_export_row_counts_match_iter_samples(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=1
            ),
        ),
        seeds=(1,),
    )
    planned_run = plan_runs(spec)[0]

    expected_observations: list[Observation] = []
    expected_ground_truth: list[GroundTruthRecord] = []
    for sample in iter_samples(planned_run.run_config):
        expected_observations.extend(sample.observations)
        expected_ground_truth.extend(sample.ground_truth)

    result, telemetry_path, ground_truth_path = _export_single_run(
        tmp_path, planned_run
    )

    assert result.observation_count == len(expected_observations)
    assert result.ground_truth_row_count == len(expected_ground_truth)
    assert pq.read_table(telemetry_path).num_rows == len(expected_observations)
    assert pq.read_table(ground_truth_path).num_rows == len(expected_ground_truth)


def test_exported_values_match_direct_iter_samples_output(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=1
            ),
        ),
        seeds=(1,),
    )
    planned_run = plan_runs(spec)[0]

    expected_values = [
        observation.value
        for sample in iter_samples(planned_run.run_config)
        for observation in sample.observations
    ]

    _, telemetry_path, _ = _export_single_run(tmp_path, planned_run)
    exported_values = pq.read_table(telemetry_path).column("value").to_pylist()

    assert exported_values == expected_values


def test_every_observation_is_exported_exactly_once(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.COOLING_DEGRADATION,
                run_count=1,
                fault_start_sim_seconds=60.0,
                fault_duration_sim_seconds=120.0,
                fault_severity=1.0,
            ),
        ),
        seeds=(1,),
    )
    planned_run = plan_runs(spec)[0]

    _, telemetry_path, _ = _export_single_run(tmp_path, planned_run)
    observation_ids = pq.read_table(telemetry_path).column("observation_id").to_pylist()

    assert len(observation_ids) == len(set(observation_ids))


def test_every_ground_truth_record_is_exported_exactly_once(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
                run_count=1,
                fault_start_sim_seconds=60.0,
                fault_duration_sim_seconds=120.0,
                fault_severity=1.0,
            ),
        ),
        seeds=(1,),
    )
    planned_run = plan_runs(spec)[0]

    _, _, ground_truth_path = _export_single_run(tmp_path, planned_run)
    table = pq.read_table(ground_truth_path)
    keys = list(
        zip(
            table.column("simulation_run_id").to_pylist(),
            table.column("asset_id").to_pylist(),
            table.column("elapsed_sim_seconds").to_pylist(),
            strict=True,
        )
    )

    assert len(keys) == len(set(keys))


def test_noisy_derived_telemetry_remains_consistent_after_export(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    """Round-trips the PR163 raw/derived consistency guarantee through an
    actual Parquet write+read: `power_output` in the exported file must
    still satisfy its formula against the exported (noisy) `voltage`/
    `current`, not the clean hidden state.
    """
    spec = spec_factory(
        scenario_plans=(
            ScenarioRunSpec(
                scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=1
            ),
        ),
        seeds=(1,),
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.03),
            SensorNoiseConfig(measurement_name="current", standard_deviation=8.0),
        ),
    )
    planned_run = plan_runs(spec)[0]

    _, telemetry_path, _ = _export_single_run(tmp_path, planned_run)
    table = pq.read_table(telemetry_path)
    rows = table.to_pylist()

    by_sample: dict[tuple[str, float], dict[str, float]] = {}
    for row in rows:
        if row["asset_id"] != planned_run.run_config.target_asset_id:
            continue
        key = (row["asset_id"], row["elapsed_sim_seconds"])
        by_sample.setdefault(key, {})[row["measurement_type"]] = row["value"]

    checked = 0
    for values in by_sample.values():
        if "power_output" not in values:
            continue
        expected_power = round((values["voltage"] * values["current"]) / 1000.0, 4)
        assert values["power_output"] == pytest.approx(expected_power, abs=1e-3)
        checked += 1
    assert checked > 0


def test_all_supported_classes_can_be_exported(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    scenarios = (
        DatasetScenario.NORMAL_OPERATION,
        DatasetScenario.COOLING_DEGRADATION,
        DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
        DatasetScenario.SENSOR_ANOMALY,
    )
    for scenario_name in scenarios:
        if scenario_name is DatasetScenario.NORMAL_OPERATION:
            plan = ScenarioRunSpec(scenario_name=scenario_name, run_count=1)
        else:
            plan = ScenarioRunSpec(
                scenario_name=scenario_name,
                run_count=1,
                fault_start_sim_seconds=60.0,
                fault_duration_sim_seconds=120.0,
                fault_severity=1.0,
            )
        spec = spec_factory(
            scenario_plans=(plan,),
            seeds=(1,),
            output_directory=str(tmp_path / scenario_name.value),
        )
        planned_run = plan_runs(spec)[0]
        run_tmp = tmp_path / f"export-{scenario_name.value}"
        run_tmp.mkdir()
        result, _, _ = _export_single_run(run_tmp, planned_run)

        assert result.observation_count > 0
        assert result.ground_truth_row_count > 0


def test_build_runs_table_row_count_and_status(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(seeds=(1, 2, 3, 4))
    planned_runs = plan_runs(spec)

    results: list[RunExportResult] = []
    for planned_run in planned_runs:
        run_tmp = tmp_path / planned_run.simulation_run_id
        run_tmp.mkdir()
        result, _, _ = _export_single_run(run_tmp, planned_run)
        results.append(result)

    table = build_runs_table(tuple(results))
    assert table.num_rows == len(planned_runs)
    assert set(table.column("status").to_pylist()) == {"success"}
    assert table.column("simulation_run_id").to_pylist() == [
        r.simulation_run_id for r in planned_runs
    ]
