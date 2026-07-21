"""`TelemetrySample.from_observations` specifications (spec section 4 /
test item "Telemetry validation")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.simulator.inference.telemetry import (
    REQUIRED_MEASUREMENTS,
    DuplicateMeasurementError,
    InconsistentSampleError,
    MissingMeasurementError,
    NonFiniteTelemetryValueError,
    TelemetrySample,
    TelemetryUnitMismatchError,
    UnsupportedMeasurementError,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_ASSET_ID = "fuel-cell-stack-01"
_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)

_CANONICAL_UNITS = {
    "stack_temperature": "celsius",
    "stack_pressure": "kPa",
    "current": "A",
    "voltage": "V",
    "fuel_flow": "SLPM",
    "power_output": "kW",
    "coolant_flow": "L/min",
}


def _observation(
    measurement: str, value: float, *, unit: str | None = None
) -> Observation:
    return Observation(
        id=f"obs-{measurement}",
        asset_id=_ASSET_ID,
        timestamp=_TIMESTAMP,
        measurement_type=MeasurementType(name=measurement),
        value=value,
        unit=unit or _CANONICAL_UNITS[measurement],
    )


def _complete_observations(**overrides: float) -> list[Observation]:
    values = {"stack_temperature": 65.0, "stack_pressure": 200.0, "current": 100.0,
              "voltage": 0.72, "fuel_flow": 2.0, "power_output": 72.0,
              "coolant_flow": 15.0}
    values.update(overrides)
    return [_observation(name, value) for name, value in values.items()]


def test_complete_canonical_sample_is_accepted() -> None:
    sample = TelemetrySample.from_observations(_complete_observations())
    assert sample.asset_id == _ASSET_ID
    assert sample.timestamp == _TIMESTAMP
    assert set(REQUIRED_MEASUREMENTS) <= set(sample.values)


def test_missing_measurement_rejected() -> None:
    observations = _complete_observations()
    without_voltage = [o for o in observations if o.measurement_type.name != "voltage"]
    with pytest.raises(MissingMeasurementError, match="voltage"):
        TelemetrySample.from_observations(without_voltage)


def test_duplicate_measurement_rejected() -> None:
    observations = _complete_observations()
    observations.append(_observation("voltage", 0.70))
    with pytest.raises(DuplicateMeasurementError):
        TelemetrySample.from_observations(observations)


def test_unit_mismatch_rejected() -> None:
    observations = _complete_observations()
    observations = [
        _observation("voltage", 0.72, unit="millivolts")
        if o.measurement_type.name == "voltage"
        else o
        for o in observations
    ]
    with pytest.raises(TelemetryUnitMismatchError):
        TelemetrySample.from_observations(observations)


def test_unknown_measurement_rejected() -> None:
    observations = _complete_observations()
    observations.append(
        Observation(
            id="obs-bogus",
            asset_id=_ASSET_ID,
            timestamp=_TIMESTAMP,
            measurement_type=MeasurementType(name="ambient_humidity"),
            value=50.0,
            unit="percent",
        )
    )
    with pytest.raises(UnsupportedMeasurementError):
        TelemetrySample.from_observations(observations)


def test_non_finite_value_rejected() -> None:
    observations = _complete_observations(current=float("nan"))
    with pytest.raises(NonFiniteTelemetryValueError):
        TelemetrySample.from_observations(observations)


def test_infinite_value_rejected() -> None:
    observations = _complete_observations(voltage=float("inf"))
    with pytest.raises(NonFiniteTelemetryValueError):
        TelemetrySample.from_observations(observations)


def test_efficiency_is_supported_but_not_required() -> None:
    observations = _complete_observations()
    observations.append(_observation("efficiency", 95.0, unit="percent"))
    sample = TelemetrySample.from_observations(observations)
    assert sample.values["efficiency"] == 95.0


def test_mixed_assets_rejected() -> None:
    observations = _complete_observations()
    observations.append(
        Observation(
            id="obs-other-asset",
            asset_id="fuel-cell-stack-02",
            timestamp=_TIMESTAMP,
            measurement_type=MeasurementType(name="efficiency"),
            value=90.0,
            unit="percent",
        )
    )
    with pytest.raises(InconsistentSampleError):
        TelemetrySample.from_observations(observations)


def test_mixed_timestamps_rejected() -> None:
    observations = _complete_observations()
    observations.append(
        Observation(
            id="obs-other-time",
            asset_id=_ASSET_ID,
            timestamp=_TIMESTAMP + timedelta(seconds=10),
            measurement_type=MeasurementType(name="efficiency"),
            value=90.0,
            unit="percent",
        )
    )
    with pytest.raises(InconsistentSampleError):
        TelemetrySample.from_observations(observations)


def test_empty_observations_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        TelemetrySample.from_observations([])


def test_sample_carries_no_evaluation_only_fields() -> None:
    """Structural proof the contract cannot carry labels/fault metadata/
    simulation run ids/dataset ids/scenario names/severity/split — the
    dataclass simply has no such field."""
    sample = TelemetrySample.from_observations(_complete_observations())
    field_names = {f for f in sample.__dataclass_fields__}
    forbidden = {
        "class_label",
        "fault_type",
        "fault_severity",
        "simulation_run_id",
        "dataset_id",
        "scenario_name",
        "split",
    }
    assert field_names.isdisjoint(forbidden)
