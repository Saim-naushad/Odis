"""Shared fixtures for PR164 dataset-generation tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.operating_conditions import (
    OperatingConditionRanges,
    SensorNoiseConfig,
)
from backend.simulator.dataset.run_config import DatasetScenario

DEFAULT_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)

# What `spec_factory` (below) yields: a keyword-only builder for a valid
# `DatasetSpec`, with sensible defaults for every field a given test
# doesn't care about overriding.
SpecFactory = Callable[..., DatasetSpec]


def default_scenario_plans() -> tuple[ScenarioRunSpec, ...]:
    return (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=2,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=1.0,
        ),
    )


@pytest.fixture
def spec_factory(tmp_path: Path) -> SpecFactory:
    def _make(
        *,
        dataset_id: str = "test-dataset",
        scenario_plans: tuple[ScenarioRunSpec, ...] | None = None,
        seeds: tuple[int, ...] | None = None,
        target_asset_ids: tuple[str, ...] = (
            "fuel-cell-stack-01",
            "fuel-cell-stack-02",
        ),
        duration_sim_seconds: float = 300.0,
        dt_seconds: float = 30.0,
        run_start_time: datetime = DEFAULT_RUN_START,
        operating_condition_ranges: OperatingConditionRanges | None = None,
        sensor_noise: tuple[SensorNoiseConfig, ...] = (),
        split_proportions: SplitProportions | None = None,
        output_directory: str | None = None,
    ) -> DatasetSpec:
        plans = (
            scenario_plans if scenario_plans is not None else default_scenario_plans()
        )
        total = sum(plan.run_count for plan in plans)
        resolved_seeds = seeds if seeds is not None else tuple(range(1, total + 1))
        return DatasetSpec(
            dataset_id=dataset_id,
            simulator_version="1.0.0",
            scenario_plans=plans,
            seeds=resolved_seeds,
            target_asset_ids=target_asset_ids,
            duration_sim_seconds=duration_sim_seconds,
            dt_seconds=dt_seconds,
            run_start_time=run_start_time,
            operating_condition_ranges=(
                operating_condition_ranges or OperatingConditionRanges()
            ),
            sensor_noise=sensor_noise,
            split_proportions=(
                split_proportions
                or SplitProportions(train=0.5, validation=0.25, test=0.25)
            ),
            output_directory=str(output_directory or (tmp_path / "output")),
        )

    return _make
