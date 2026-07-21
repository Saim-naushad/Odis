"""DatasetSpec / ScenarioRunSpec / SplitProportions specifications."""

from dataclasses import replace

import pytest

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.fault_variation import (
    FaultSeverityRange,
    FaultTimingRange,
)
from backend.simulator.dataset.operating_conditions import (
    NoiseRegime,
    SensorNoiseConfig,
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


# --- ScenarioRunSpec: fixed-vs-ranged fault contract ------------------------


def test_fault_scenario_requires_a_fault_start_representation() -> None:
    with pytest.raises(
        ValueError, match=r"fault_start_sim_seconds.*fault_start_range"
    ):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_duration_sim_seconds=120.0,
            fault_severity=0.5,
        )


def test_fault_scenario_rejects_both_fixed_and_ranged_start() -> None:
    with pytest.raises(ValueError, match="both fault_start_sim_seconds"):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_start_sim_seconds=60.0,
            fault_start_range=FaultTimingRange(
                minimum_seconds=60.0, maximum_seconds=120.0, step_seconds=10.0
            ),
            fault_duration_sim_seconds=120.0,
            fault_severity=0.5,
        )


def test_fault_scenario_requires_a_severity_representation() -> None:
    with pytest.raises(ValueError, match=r"fault_severity.*fault_severity_range"):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
        )


def test_fault_scenario_rejects_both_fixed_and_ranged_severity() -> None:
    with pytest.raises(ValueError, match="both fault_severity"):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=0.5,
            fault_severity_range=FaultSeverityRange(minimum=0.2, maximum=0.8),
        )


def test_healthy_scenario_rejects_a_fault_start_range() -> None:
    with pytest.raises(ValueError, match="does not support a fault window"):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION,
            run_count=1,
            fault_start_range=FaultTimingRange(
                minimum_seconds=60.0, maximum_seconds=120.0, step_seconds=10.0
            ),
        )


def test_healthy_scenario_rejects_a_severity_range() -> None:
    with pytest.raises(ValueError, match="does not support fault_severity_range"):
        ScenarioRunSpec(
            scenario_name=DatasetScenario.NORMAL_OPERATION,
            run_count=1,
            fault_severity_range=FaultSeverityRange(minimum=0.2, maximum=0.8),
        )


def test_ranged_scenario_run_spec_json_round_trip() -> None:
    plan = ScenarioRunSpec(
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        run_count=16,
        fault_start_range=FaultTimingRange(
            minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
        ),
        fault_duration_sim_seconds=240.0,
        fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
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


def test_duplicate_scenario_name_across_plans_is_rejected(
    spec_factory: SpecFactory,
) -> None:
    """Two plans for the same class would collide on run ID (`local_index`
    restarts at 0 per plan) — reject at spec construction rather than
    silently producing two runs sharing one `simulation_run_id`.
    """
    plans = (
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=0.5,
        ),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=1,
            fault_start_sim_seconds=90.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=0.9,
        ),
    )
    spec = spec_factory()
    with pytest.raises(ValueError, match="must not repeat a scenario_name"):
        replace(spec, scenario_plans=plans, seeds=(1, 2))


def test_fault_start_range_exceeding_duration_is_rejected(
    spec_factory: SpecFactory,
) -> None:
    ranged_plan = ScenarioRunSpec(
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        run_count=1,
        fault_start_range=FaultTimingRange(
            minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
        ),
        fault_duration_sim_seconds=240.0,
        fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
    )
    spec = spec_factory()
    # duration_sim_seconds=300.0 (spec_factory default): max grid value 420 +
    # duration 240 = 660, far beyond 300 — every candidate at the top of the
    # grid would produce an out-of-range fault window.
    with pytest.raises(ValueError, match="exceeds duration_sim_seconds"):
        replace(
            spec,
            scenario_plans=(ranged_plan,),
            seeds=(1,),
            duration_sim_seconds=300.0,
        )


def test_fault_start_range_within_duration_is_accepted(
    spec_factory: SpecFactory,
) -> None:
    ranged_plan = ScenarioRunSpec(
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        run_count=1,
        fault_start_range=FaultTimingRange(
            minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
        ),
        fault_duration_sim_seconds=240.0,
        fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
    )
    spec = spec_factory()
    resolved = replace(
        spec,
        scenario_plans=(ranged_plan,),
        seeds=(1,),
        duration_sim_seconds=900.0,
    )
    assert resolved.total_run_count == 1


# --- DatasetSpec: JSON round trip -------------------------------------------


def test_dataset_spec_json_round_trip(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec


def test_dataset_spec_json_round_trip_with_sensor_noise(
    spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.01),
            SensorNoiseConfig(measurement_name="current", standard_deviation=2.0),
        )
    )
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec


def test_dataset_spec_json_round_trip_with_ranged_fault_plans(
    spec_factory: SpecFactory,
) -> None:
    plans = (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=2),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=4,
            fault_start_range=FaultTimingRange(
                minimum_seconds=90.0, maximum_seconds=420.0, step_seconds=10.0
            ),
            fault_duration_sim_seconds=240.0,
            fault_severity_range=FaultSeverityRange(minimum=0.15, maximum=1.0),
        ),
    )
    spec = spec_factory(
        scenario_plans=plans, seeds=tuple(range(1, 7)), duration_sim_seconds=900.0
    )
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec


# --- DatasetSpec: sensor_noise_regimes (PR174) ------------------------------

_NOMINAL_REGIME = NoiseRegime(
    name="nominal",
    sensor_noise=(
        SensorNoiseConfig(measurement_name="stack_temperature", standard_deviation=0.3),
    ),
)
_MODERATE_REGIME = NoiseRegime(
    name="moderate",
    sensor_noise=(
        SensorNoiseConfig(
            measurement_name="stack_temperature", standard_deviation=0.45
        ),
    ),
)
_HIGH_REGIME = NoiseRegime(
    name="high_bounded",
    sensor_noise=(
        SensorNoiseConfig(measurement_name="stack_temperature", standard_deviation=0.6),
    ),
)


def test_sensor_noise_regimes_reject_a_single_regime(
    spec_factory: SpecFactory,
) -> None:
    spec = spec_factory()
    with pytest.raises(ValueError, match="at least 2 regimes"):
        replace(spec, sensor_noise=(), sensor_noise_regimes=(_NOMINAL_REGIME,))


def test_sensor_noise_regimes_reject_duplicate_names(
    spec_factory: SpecFactory,
) -> None:
    spec = spec_factory()
    duplicate = NoiseRegime(name="nominal", sensor_noise=_HIGH_REGIME.sensor_noise)
    with pytest.raises(ValueError, match="must not repeat a name"):
        replace(
            spec,
            sensor_noise=(),
            sensor_noise_regimes=(_NOMINAL_REGIME, duplicate),
        )


def test_sensor_noise_and_sensor_noise_regimes_are_mutually_exclusive(
    spec_factory: SpecFactory,
) -> None:
    spec = spec_factory(
        sensor_noise=(
            SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.01),
        )
    )
    with pytest.raises(ValueError, match="cannot set both sensor_noise"):
        replace(
            spec,
            sensor_noise_regimes=(_NOMINAL_REGIME, _MODERATE_REGIME, _HIGH_REGIME),
        )


def test_sensor_noise_regimes_are_accepted_when_sensor_noise_is_empty(
    spec_factory: SpecFactory,
) -> None:
    spec = spec_factory(
        sensor_noise=(),
        sensor_noise_regimes=(_NOMINAL_REGIME, _MODERATE_REGIME, _HIGH_REGIME),
    )
    assert spec.sensor_noise_regimes == (
        _NOMINAL_REGIME,
        _MODERATE_REGIME,
        _HIGH_REGIME,
    )


def test_dataset_spec_json_round_trip_with_sensor_noise_regimes(
    spec_factory: SpecFactory,
) -> None:
    spec = spec_factory(
        sensor_noise=(),
        sensor_noise_regimes=(_NOMINAL_REGIME, _MODERATE_REGIME, _HIGH_REGIME),
    )
    restored = DatasetSpec.from_json_dict(spec.to_json_dict())
    assert restored == spec
