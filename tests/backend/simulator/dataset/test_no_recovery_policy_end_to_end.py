"""End-to-end, full-dataset-generation proof of the no-recovery policy
(PR167 blocking-review correction).

Generates one real dataset (`generate_dataset`, the same pipeline
`datasets/pem-faults-pilot` is built from) covering all three fault
classes, then reads `runs.parquet`/`ground_truth.parquet` back from disk
and proves directly: no target-asset row at or after its run's
`fault_start_sim_seconds` is ever labeled healthy (`fault_active=False`),
for every fault run in the dataset — not just one hand-built `RunConfig`.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
from backend.simulator.dataset.generate import generate_dataset
from backend.simulator.dataset.run_config import DatasetScenario

from .conftest import SpecFactory

_FAULT_START = 90.0
_FAULT_DURATION = 180.0
_FAULT_SEVERITY = 1.0


def _all_fault_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.SENSOR_ANOMALY,
            run_count=2,
            fault_start_sim_seconds=_FAULT_START,
            fault_duration_sim_seconds=_FAULT_DURATION,
            fault_severity=_FAULT_SEVERITY,
        ),
    )


def test_no_target_asset_row_is_healthy_while_fault_remains_applied(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        dataset_id="no-recovery-e2e",
        scenario_plans=_all_fault_scenario_plans(),
        seeds=tuple(range(1, 9)),
        target_asset_ids=("fuel-cell-stack-01", "fuel-cell-stack-02"),
        duration_sim_seconds=450.0,  # well past ramp end (90+180=270)
        dt_seconds=10.0,
        output_directory=str(tmp_path / "dataset"),
    )
    result = generate_dataset(spec, generation_command="test")

    runs = pq.read_table(result.output_directory / "runs.parquet").to_pylist()
    ground_truth = pq.read_table(
        result.output_directory / "ground_truth.parquet"
    ).to_pylist()
    runs_by_id = {row["simulation_run_id"]: row for row in runs}

    fault_runs = [row for row in runs if row["class_label"] != "normal_operation"]
    assert fault_runs, "fixture must include fault runs"

    checked_post_ramp_rows = 0
    for row in ground_truth:
        run = runs_by_id[row["simulation_run_id"]]
        if run["class_label"] == "normal_operation":
            continue
        if row["asset_id"] != run["target_asset_id"]:
            continue
        if row["elapsed_sim_seconds"] < run["fault_start_sim_seconds"]:
            continue

        assert row["fault_active"] is True, (
            f"run={row['simulation_run_id']} asset={row['asset_id']} "
            f"elapsed={row['elapsed_sim_seconds']} is on/after fault_start "
            f"({run['fault_start_sim_seconds']}) but is labeled healthy"
        )
        ramp_end = run["fault_start_sim_seconds"] + run["fault_duration_sim_seconds"]
        if row["elapsed_sim_seconds"] >= ramp_end:
            assert row["fault_severity"] == 1.0, (
                f"run={row['simulation_run_id']} elapsed={row['elapsed_sim_seconds']} "
                "is past ramp end but not at maximum severity"
            )
            checked_post_ramp_rows += 1

    assert checked_post_ramp_rows > 0, "fixture must include post-ramp samples"
