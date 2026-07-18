"""Raw/derived telemetry consistency specifications (PR163 correction).

Covers the risk the correction closes: a dataset sample must never mix
noisy core measurements with derived measurements silently computed from
clean, hidden machine state — that would leak state a real inference
system could never see, and let a model bypass sensor noise by reading the
clean derived channel instead of the noisy core one.
"""

import random
from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.telemetry import build_sample_observations
from backend.simulator.machine import FuelCellMachine
from backend.simulator.telemetry import TelemetryContext, observations_from_machine
from domain.entities.observation import Observation

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


class _FixedNoise(random.Random):
    """A `random.Random` whose `.gauss()` always returns a fixed value.

    Makes "substantial deterministic noise" exact and reviewable, rather
    than depending on the statistical behavior of a real seeded stream.
    """

    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        del mu, sigma
        return self._value


def _machine() -> FuelCellMachine:
    machine = FuelCellMachine.default()
    machine.set_target_load(70.0)
    for _ in range(20):
        machine.tick(5.0)
    return machine


# --- No-noise preservation ---------------------------------------------------


def test_no_noise_matches_observations_from_machine_exactly() -> None:
    machine = _machine()
    context = TelemetryContext(run_id="dataset-telemetry-test")
    rng = random.Random("unused")

    expected = observations_from_machine(machine, timestamp=_TIMESTAMP, context=context)
    actual = build_sample_observations(
        machine, timestamp=_TIMESTAMP, context=context, noise_configs=(), rng=rng
    )

    assert actual == expected


def test_no_noise_does_not_touch_the_rng() -> None:
    machine = _machine()
    context = TelemetryContext(run_id="dataset-telemetry-test")
    rng = random.Random("seed")
    state_before = rng.getstate()

    build_sample_observations(
        machine, timestamp=_TIMESTAMP, context=context, noise_configs=(), rng=rng
    )

    assert rng.getstate() == state_before


# --- Consistency: derived values match their formula from emitted core -----


def test_derived_values_are_consistent_with_emitted_noisy_core_values() -> None:
    machine = _machine()
    context = TelemetryContext(run_id="dataset-telemetry-test")
    noise_configs = (
        SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.02),
        SensorNoiseConfig(measurement_name="current", standard_deviation=5.0),
        SensorNoiseConfig(measurement_name="fuel_flow", standard_deviation=0.2),
    )

    observations = build_sample_observations(
        machine,
        timestamp=_TIMESTAMP,
        context=context,
        noise_configs=noise_configs,
        rng=random.Random("seed"),
    )
    by_name = {obs.measurement_type.name: obs.value for obs in observations}

    expected_power_kw = (by_name["voltage"] * by_name["current"]) / 1000.0
    fuel_energy = max(by_name["fuel_flow"] * 0.033, 1e-6)
    expected_efficiency = min(100.0, (expected_power_kw / fuel_energy) * 100.0)

    assert by_name["power_output"] == pytest.approx(expected_power_kw, abs=1e-3)
    assert by_name["efficiency"] == pytest.approx(expected_efficiency, abs=1e-2)


def test_no_emitted_derived_observation_matches_the_clean_state_computation() -> None:
    """With noise active, `power_output` must not equal what clean state
    alone would have produced — if it did, the noisy core measurement next
    to it would be inconsistent with it (the original bug).
    """
    machine = _machine()
    clean_state = machine.state
    clean_power_kw = round((clean_state.voltage * clean_state.current) / 1000.0, 4)

    context = TelemetryContext(run_id="dataset-telemetry-test")
    noise_configs = (
        SensorNoiseConfig(measurement_name="current", standard_deviation=40.0),
    )
    observations = build_sample_observations(
        machine,
        timestamp=_TIMESTAMP,
        context=context,
        noise_configs=noise_configs,
        rng=_FixedNoise(40.0),  # a large, exact, deterministic shift
    )
    by_name = {obs.measurement_type.name: obs.value for obs in observations}

    assert by_name["current"] != pytest.approx(clean_state.current)
    assert by_name["power_output"] != pytest.approx(clean_power_kw)


# --- Leakage regression -------------------------------------------------------


def test_substantial_noise_on_current_changes_power_output_consistently() -> None:
    """This is the direct regression for the reported bug: a core
    measurement (`current`) receives a large, exact, known noise value, and
    the derived `power_output` must move by exactly the amount that noisy
    current implies — not stay at the clean-state value.

    Under the old "noisy core + clean derived" behavior, `power_output`
    here would equal `clean_state.voltage * clean_state.current / 1000`
    regardless of the noise, and this test would fail.
    """
    machine = _machine()
    clean_state = machine.state
    context = TelemetryContext(run_id="dataset-telemetry-test")
    noise_value = 60.0
    noise_configs = (
        SensorNoiseConfig(
            measurement_name="current", standard_deviation=1.0, clip_std_multiple=None
        ),
    )

    observations = build_sample_observations(
        machine,
        timestamp=_TIMESTAMP,
        context=context,
        noise_configs=noise_configs,
        rng=_FixedNoise(noise_value),
    )
    by_name = {obs.measurement_type.name: obs.value for obs in observations}

    expected_noisy_current = round(clean_state.current + noise_value, 4)
    expected_power_kw = round(
        (clean_state.voltage * expected_noisy_current) / 1000.0, 4
    )
    clean_power_kw = round((clean_state.voltage * clean_state.current) / 1000.0, 4)

    assert by_name["current"] == pytest.approx(expected_noisy_current)
    assert by_name["power_output"] == pytest.approx(expected_power_kw)
    assert by_name["power_output"] != pytest.approx(clean_power_kw)


# --- Only noise-eligible dependents are affected ------------------------------


def test_coolant_flow_is_unaffected_by_core_noise() -> None:
    """`coolant_flow` derives from `load`/`cooling_efficiency`, neither of
    which is a core measurement or a valid sensor-noise target — so it must
    be identical whether or not core noise is configured, in either policy.
    """
    machine = _machine()
    context = TelemetryContext(run_id="dataset-telemetry-test")

    clean = build_sample_observations(
        machine,
        timestamp=_TIMESTAMP,
        context=context,
        noise_configs=(),
        rng=random.Random("a"),
    )
    noisy = build_sample_observations(
        machine,
        timestamp=_TIMESTAMP,
        context=context,
        noise_configs=(
            SensorNoiseConfig(measurement_name="current", standard_deviation=50.0),
        ),
        rng=_FixedNoise(50.0),
    )

    def _coolant_flow(observations: tuple[Observation, ...]) -> float:
        return next(
            o.value for o in observations if o.measurement_type.name == "coolant_flow"
        )

    assert _coolant_flow(clean) == _coolant_flow(noisy)
