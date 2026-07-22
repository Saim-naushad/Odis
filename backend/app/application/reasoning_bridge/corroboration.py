"""Deterministic corroboration rules (spec sections 7-9).

Reuses `src.application.trend_detector.TrendDetector` — the codebase's
own existing, calibrated trend primitive — over recent observations for
each fault class's relevant measurements. Never reuses the model's own
class probabilities as a rule input, and never treats a model score as
"probability the fault is real" (spec section 9): scores are not read by
any function in this module at all.

Every rule that fires is recorded by a stable, documented rule id
(`<fault_class>.<condition>`) so `AiFaultEvidence.corroboration_rule_ids`
and the published reasoning-result event carry a traceable "why", not
just a bare verdict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.trend_detector import TrendDetector
from backend.app.domain.ai_fault_evidence import CorroborationResult
from domain.entities.observation import Observation
from domain.value_objects.trend_direction import TrendDirection

# Below this many observations for a measurement, even a `STABLE` read is
# not trustworthy enough to corroborate or refute anything.
MIN_OBSERVATIONS_FOR_TREND = 4

_detector = TrendDetector()


@dataclass(frozen=True)
class CorroborationOutcome:
    result: CorroborationResult
    rule_ids: tuple[str, ...]
    notes: str
    supporting_observation_ids: tuple[str, ...]


def _trend(observations: Sequence[Observation]) -> TrendDirection | None:
    if len(observations) < MIN_OBSERVATIONS_FOR_TREND:
        return None
    return _detector.detect(observations).direction


def _ids(*groups: Sequence[Observation]) -> tuple[str, ...]:
    seen: list[str] = []
    for group in groups:
        for observation in group:
            if observation.id not in seen:
                seen.append(observation.id)
    return tuple(seen)


def corroborate_cooling_degradation(
    *,
    stack_temperature: Sequence[Observation],
    coolant_flow: Sequence[Observation],
) -> CorroborationOutcome:
    """Cooling degradation: a sustained stack-temperature rise not offset
    by increasing coolant flow (spec section 7's cooling-degradation
    example)."""
    temperature_trend = _trend(stack_temperature)
    coolant_trend = _trend(coolant_flow)
    ids = _ids(stack_temperature, coolant_flow)

    if temperature_trend is None:
        return CorroborationOutcome(
            "insufficient_evidence",
            ("cooling_degradation.insufficient_stack_temperature_history",),
            "Not enough stack_temperature history to corroborate or refute.",
            ids,
        )

    if temperature_trend is not TrendDirection.INCREASING:
        return CorroborationOutcome(
            "not_corroborated",
            ("cooling_degradation.stack_temperature_not_increasing",),
            f"stack_temperature trend is {temperature_trend.value}, not increasing.",
            ids,
        )

    if coolant_trend is None:
        return CorroborationOutcome(
            "partially_corroborated",
            (
                "cooling_degradation.stack_temperature_increasing",
                "cooling_degradation.insufficient_coolant_flow_history",
            ),
            "stack_temperature is increasing, but coolant_flow history is "
            "insufficient to assess whether cooling is compensating.",
            ids,
        )

    if coolant_trend is TrendDirection.INCREASING:
        return CorroborationOutcome(
            "not_corroborated",
            (
                "cooling_degradation.stack_temperature_increasing",
                "cooling_degradation.coolant_flow_increasing_contradicts",
            ),
            "coolant_flow is increasing alongside stack_temperature, "
            "consistent with active compensation rather than degradation.",
            ids,
        )

    if coolant_trend is TrendDirection.STABLE:
        return CorroborationOutcome(
            "partially_corroborated",
            (
                "cooling_degradation.stack_temperature_increasing",
                "cooling_degradation.coolant_flow_stable",
            ),
            "stack_temperature is increasing while coolant_flow is stable — "
            "consistent with, but not conclusive for, cooling degradation.",
            ids,
        )

    return CorroborationOutcome(
        "corroborated",
        (
            "cooling_degradation.stack_temperature_increasing",
            "cooling_degradation.coolant_flow_decreasing",
        ),
        "stack_temperature is increasing while coolant_flow is decreasing — "
        "cooling capacity is not compensating for the rising temperature.",
        ids,
    )


def corroborate_hydrogen_supply_issue(
    *,
    fuel_flow: Sequence[Observation],
    voltage: Sequence[Observation],
) -> CorroborationOutcome:
    """Hydrogen supply issue: reduced fuel flow with a depressed voltage
    response, consistent with starvation rather than a load change alone
    (spec section 7's hydrogen-supply example)."""
    fuel_flow_trend = _trend(fuel_flow)
    voltage_trend = _trend(voltage)
    ids = _ids(fuel_flow, voltage)

    if fuel_flow_trend is None:
        return CorroborationOutcome(
            "insufficient_evidence",
            ("hydrogen_supply_issue.insufficient_fuel_flow_history",),
            "Not enough fuel_flow history to corroborate or refute.",
            ids,
        )

    if fuel_flow_trend is not TrendDirection.DECREASING:
        return CorroborationOutcome(
            "not_corroborated",
            ("hydrogen_supply_issue.fuel_flow_not_decreasing",),
            f"fuel_flow trend is {fuel_flow_trend.value}, not decreasing.",
            ids,
        )

    if voltage_trend is None:
        return CorroborationOutcome(
            "partially_corroborated",
            (
                "hydrogen_supply_issue.fuel_flow_decreasing",
                "hydrogen_supply_issue.insufficient_voltage_history",
            ),
            "fuel_flow is decreasing, but voltage history is insufficient to "
            "assess whether the response is consistent with starvation.",
            ids,
        )

    if voltage_trend is not TrendDirection.DECREASING:
        return CorroborationOutcome(
            "partially_corroborated",
            (
                "hydrogen_supply_issue.fuel_flow_decreasing",
                "hydrogen_supply_issue.voltage_not_decreasing",
            ),
            "fuel_flow is decreasing but voltage is not — consistent with a "
            "commanded load reduction rather than a supply issue alone.",
            ids,
        )

    return CorroborationOutcome(
        "corroborated",
        (
            "hydrogen_supply_issue.fuel_flow_decreasing",
            "hydrogen_supply_issue.voltage_decreasing",
        ),
        "fuel_flow and voltage are both decreasing, consistent with hydrogen "
        "starvation rather than a load change alone.",
        ids,
    )


def corroborate_sensor_anomaly(
    *,
    stack_temperature: Sequence[Observation],
    current: Sequence[Observation],
    voltage: Sequence[Observation],
    fuel_flow: Sequence[Observation],
) -> CorroborationOutcome:
    """Sensor anomaly: a temperature-reading shift with no corresponding
    change in the physically related signals (spec section 7's
    sensor-anomaly example) — physical consistency across current/
    voltage/fuel_flow instead *contradicts* the sensor-anomaly hypothesis
    (it looks like a real physical event)."""
    temperature_trend = _trend(stack_temperature)
    ids = _ids(stack_temperature, current, voltage, fuel_flow)

    if temperature_trend is None:
        return CorroborationOutcome(
            "insufficient_evidence",
            ("sensor_anomaly.insufficient_stack_temperature_history",),
            "Not enough stack_temperature history to corroborate or refute.",
            ids,
        )

    if temperature_trend is TrendDirection.STABLE:
        return CorroborationOutcome(
            "not_corroborated",
            ("sensor_anomaly.stack_temperature_stable",),
            "stack_temperature shows no shift, so there is nothing for a "
            "sensor anomaly to explain.",
            ids,
        )

    related_trends = [_trend(current), _trend(voltage), _trend(fuel_flow)]
    known_related_trends = [t for t in related_trends if t is not None]
    if not known_related_trends:
        return CorroborationOutcome(
            "partially_corroborated",
            ("sensor_anomaly.stack_temperature_shifted",),
            "stack_temperature shows a shift, but there is not enough history "
            "on the related signals to confirm physical inconsistency.",
            ids,
        )

    moved = sum(1 for t in known_related_trends if t is not TrendDirection.STABLE)
    if moved == 0:
        return CorroborationOutcome(
            "corroborated",
            (
                "sensor_anomaly.stack_temperature_shifted",
                "sensor_anomaly.related_signals_stable",
            ),
            "stack_temperature shifted while current, voltage, and fuel_flow "
            "all remained stable — physically inconsistent with a real "
            "thermal event.",
            ids,
        )
    if moved == len(known_related_trends):
        return CorroborationOutcome(
            "not_corroborated",
            (
                "sensor_anomaly.stack_temperature_shifted",
                "sensor_anomaly.related_signals_also_shifted",
            ),
            "stack_temperature shifted alongside every related signal — "
            "physically consistent with a real event, not a sensor anomaly.",
            ids,
        )
    return CorroborationOutcome(
        "partially_corroborated",
        (
            "sensor_anomaly.stack_temperature_shifted",
            "sensor_anomaly.related_signals_partially_shifted",
        ),
        "stack_temperature shifted while only some related signals moved — "
        "ambiguous between a sensor anomaly and a real event.",
        ids,
    )
