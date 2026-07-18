"""DatasetSpec / ScenarioRunSpec / SplitProportions specifications."""

from dataclasses import replace

import pytest

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.run_config import DatasetScenario

from .conftest import SpecFactory

# --- ScenarioRunSpec ----------------------------------------------------------


def test_scenario_run_spec_rejects_non_positive_run_count() -> None:
    with pytest.raises(ValueError):
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=0)


def test_scenario_run_spec_json_round_trip() -> None:
    plan = ScenarioRunSpec(
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        run_count=3,
        fault_start_sim_seconds=60.0,
        fault_duration_sim_seconds=120.0,
        fault_severity=0.75,
    )
    restored = ScenarioRunSpec.from_json_dict(plan.to_json_dict())
    assert restored == plan


# --- SplitProportions ----------------------------------------------------------


def test_split_proportions_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        SplitProportions(train=0.5, validation=0.3, test=0.3)


def test_split_proportions_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError):
        SplitProportions(train=1.5, validation=-0.5, test=0.0)


def test_split_proportions_json_round_trip() -> None:
    proportions = SplitProportions(train=0.6, validation=0.2, test=0.2)
    restored = SplitProportions.from_json_dict(proportions.to_json_dict())
    assert restored == proportions


# --- DatasetSpec: structural validation -----------------------------------


def test_valid_spec_constructs(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    assert spec.total_run_count == 4


def test_empty_dataset_id_is_rejected(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    with pytest.raises(ValueError):
        replace(spec, dataset_id="")


def test_empty_scenario_plans_is_rejected(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    with pytest.raises(ValueError):
        replace(spec, scenario_plans=())


def test_seed_count_mismatch_is_rejected(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    with pytest.raises(ValueError):
        replace(spec, seeds=(1, 2))  # spec_factory's default plans need 4 seeds


def test_naive_run_start_time_is_rejected(spec_factory: SpecFactory) -> None:
    import datetime as dt

    spec = spec_factory()
    with pytest.raises(ValueError):
        replace(spec, run_start_time=dt.datetime(2026, 1, 1))  # naive


def test_non_positive_duration_is_rejected(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    with pytest.raises(ValueError):
        replace(spec, duration_sim_seconds=0.0)


def test_unsupported_scenario_is_rejected(spec_factory: SpecFactory) -> None:
    """Membrane dehydration / any future unsupported class must be rejected
    at spec construction, not silently accepted and fail later.
    """
    spec = spec_factory()
    bad_plan = ScenarioRunSpec(scenario_name="membrane_dehydration", run_count=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(spec, scenario_plans=(bad_plan,), seeds=(1,))


# --- DatasetSpec: JSON round trip -------------------------------------------


def test_dataset_spec_json_round_trip(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec


def test_dataset_spec_json_round_trip_with_sensor_noise(
    spec_factory: SpecFactory
) -> None:
    from backend.simulator.dataset.operating_conditions import SensorNoiseConfig

    spec = spec_factory(
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.01),
            SensorNoiseConfig(measurement_name="current", standard_deviation=2.0),
        )
    )
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec
