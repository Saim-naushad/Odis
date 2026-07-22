"""Deterministic corroboration specification (PR178 spec sections 7-9, 19
"Corroboration"): for each fault class, a corroborated, partially
corroborated, not-corroborated, and insufficient-evidence case."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.application.reasoning_bridge.corroboration import (
    corroborate_cooling_degradation,
    corroborate_hydrogen_supply_issue,
    corroborate_sensor_anomaly,
)
from domain.entities.observation import Observation

from .conftest import make_observation

_ASSET_ID = "fuel-cell-stack-01"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _series(
    measurement: str, values: list[float], *, unit: str = "unit"
) -> list[Observation]:
    return [
        make_observation(
            asset_id=_ASSET_ID,
            measurement_type=measurement,
            value=value,
            unit=unit,
            timestamp=_T0 + timedelta(seconds=i * 10),
            observation_id=str(i),
        )
        for i, value in enumerate(values)
    ]


_INCREASING = [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
_DECREASING = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 10.0, 10.0, 10.0]
_STABLE = [50.0] * 10


# --- Cooling degradation ----------------------------------------------------


def test_cooling_degradation_corroborated() -> None:
    outcome = corroborate_cooling_degradation(
        stack_temperature=_series("stack_temperature", _INCREASING),
        coolant_flow=_series("coolant_flow", _DECREASING),
    )
    assert outcome.result == "corroborated"
    assert outcome.rule_ids


def test_cooling_degradation_partially_corroborated() -> None:
    outcome = corroborate_cooling_degradation(
        stack_temperature=_series("stack_temperature", _INCREASING),
        coolant_flow=_series("coolant_flow", _STABLE),
    )
    assert outcome.result == "partially_corroborated"


def test_cooling_degradation_not_corroborated_temperature_stable() -> None:
    outcome = corroborate_cooling_degradation(
        stack_temperature=_series("stack_temperature", _STABLE),
        coolant_flow=_series("coolant_flow", _STABLE),
    )
    assert outcome.result == "not_corroborated"


def test_cooling_degradation_not_corroborated_coolant_compensating() -> None:
    outcome = corroborate_cooling_degradation(
        stack_temperature=_series("stack_temperature", _INCREASING),
        coolant_flow=_series("coolant_flow", _INCREASING),
    )
    assert outcome.result == "not_corroborated"


def test_cooling_degradation_insufficient_evidence() -> None:
    outcome = corroborate_cooling_degradation(
        stack_temperature=_series("stack_temperature", [10.0, 11.0]),
        coolant_flow=_series("coolant_flow", [5.0, 5.0]),
    )
    assert outcome.result == "insufficient_evidence"


# --- Hydrogen supply issue ---------------------------------------------------


def test_hydrogen_supply_issue_corroborated() -> None:
    outcome = corroborate_hydrogen_supply_issue(
        fuel_flow=_series("fuel_flow", _DECREASING),
        voltage=_series("voltage", _DECREASING),
    )
    assert outcome.result == "corroborated"
    assert outcome.rule_ids


def test_hydrogen_supply_issue_partially_corroborated() -> None:
    outcome = corroborate_hydrogen_supply_issue(
        fuel_flow=_series("fuel_flow", _DECREASING),
        voltage=_series("voltage", _STABLE),
    )
    assert outcome.result == "partially_corroborated"


def test_hydrogen_supply_issue_not_corroborated_fuel_flow_stable() -> None:
    outcome = corroborate_hydrogen_supply_issue(
        fuel_flow=_series("fuel_flow", _STABLE),
        voltage=_series("voltage", _DECREASING),
    )
    assert outcome.result == "not_corroborated"


def test_hydrogen_supply_issue_insufficient_evidence() -> None:
    outcome = corroborate_hydrogen_supply_issue(
        fuel_flow=_series("fuel_flow", [10.0, 9.0]),
        voltage=_series("voltage", [48.0, 47.0]),
    )
    assert outcome.result == "insufficient_evidence"


# --- Sensor anomaly -----------------------------------------------------------


def test_sensor_anomaly_corroborated() -> None:
    outcome = corroborate_sensor_anomaly(
        stack_temperature=_series("stack_temperature", _INCREASING),
        current=_series("current", _STABLE),
        voltage=_series("voltage", _STABLE),
        fuel_flow=_series("fuel_flow", _STABLE),
    )
    assert outcome.result == "corroborated"
    assert outcome.rule_ids


def test_sensor_anomaly_partially_corroborated() -> None:
    outcome = corroborate_sensor_anomaly(
        stack_temperature=_series("stack_temperature", _INCREASING),
        current=_series("current", _STABLE),
        voltage=_series("voltage", _INCREASING),
        fuel_flow=_series("fuel_flow", _STABLE),
    )
    assert outcome.result == "partially_corroborated"


def test_sensor_anomaly_not_corroborated_all_signals_moved() -> None:
    outcome = corroborate_sensor_anomaly(
        stack_temperature=_series("stack_temperature", _INCREASING),
        current=_series("current", _INCREASING),
        voltage=_series("voltage", _INCREASING),
        fuel_flow=_series("fuel_flow", _INCREASING),
    )
    assert outcome.result == "not_corroborated"


def test_sensor_anomaly_not_corroborated_temperature_stable() -> None:
    outcome = corroborate_sensor_anomaly(
        stack_temperature=_series("stack_temperature", _STABLE),
        current=_series("current", _STABLE),
        voltage=_series("voltage", _STABLE),
        fuel_flow=_series("fuel_flow", _STABLE),
    )
    assert outcome.result == "not_corroborated"


def test_sensor_anomaly_insufficient_evidence() -> None:
    outcome = corroborate_sensor_anomaly(
        stack_temperature=_series("stack_temperature", [10.0, 20.0]),
        current=_series("current", [1.0, 1.0]),
        voltage=_series("voltage", [1.0, 1.0]),
        fuel_flow=_series("fuel_flow", [1.0, 1.0]),
    )
    assert outcome.result == "insufficient_evidence"


# --- Cross-cutting: never reuse model logic/probabilities -------------------


def test_corroboration_never_reads_model_scores() -> None:
    """A structural guarantee, not just behavioral: the corroboration
    functions' signatures accept only `Observation` sequences — there is
    no parameter through which a model score could influence the
    verdict."""
    import inspect

    for fn in (
        corroborate_cooling_degradation,
        corroborate_hydrogen_supply_issue,
        corroborate_sensor_anomaly,
    ):
        for name in inspect.signature(fn).parameters:
            assert "score" not in name
            assert "proba" not in name
            assert "confidence" not in name
