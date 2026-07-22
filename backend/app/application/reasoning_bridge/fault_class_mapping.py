"""Deterministic mapping from promoted-model fault classes to ODIS
reasoning-bridge concepts (spec section 6).

Only the three classes the promoted `plant_alpha_fault_v1` model actually
supports are mapped — no invented classes (e.g. "membrane dehydration"),
and `healthy` is never mapped here at all (rejected earlier, in
`input_events.validate_alert_transition`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaultClassMapping:
    """Everything the reasoning bridge needs to know about one supported
    fault class, fixed and reviewed here rather than inferred at runtime."""

    fault_class: str
    situation_type: str
    relevant_measurements: tuple[str, ...]
    operator_impact: str
    allowed_categories: tuple[str, ...]
    recommended_steps: tuple[str, ...]
    verification_steps: tuple[str, ...]


FAULT_CLASS_MAPPINGS: dict[str, FaultClassMapping] = {
    "cooling_degradation": FaultClassMapping(
        fault_class="cooling_degradation",
        situation_type="cooling_system_degradation",
        relevant_measurements=("stack_temperature", "coolant_flow", "current"),
        operator_impact=(
            "Reduced cooling capacity risks accelerated stack degradation and "
            "an eventual forced load reduction or shutdown if unaddressed."
        ),
        allowed_categories=("investigate", "monitor"),
        recommended_steps=(
            "Inspect the coolant loop for restrictions, leaks, or pump issues.",
            "Verify the coolant-flow sensor against a manual or redundant reading.",
            "Schedule a maintenance inspection of the cooling subsystem.",
            "Reduce load only if deterministic operating thresholds support it.",
        ),
        verification_steps=(
            "Cross-check stack temperature against a secondary sensor if available.",
            "Confirm coolant-flow readings are physically plausible before acting.",
        ),
    ),
    "hydrogen_supply_issue": FaultClassMapping(
        fault_class="hydrogen_supply_issue",
        situation_type="hydrogen_supply_degradation",
        relevant_measurements=("fuel_flow", "voltage", "current", "power_output"),
        operator_impact=(
            "Reduced hydrogen supply risks stack starvation, voltage instability, "
            "and lost power output if unaddressed."
        ),
        allowed_categories=("investigate", "monitor"),
        recommended_steps=(
            "Inspect the hydrogen supply path for restrictions or leaks.",
            "Check regulator/valve pressure against the expected setpoint.",
            "Verify fuel-flow instrumentation against a redundant reading.",
            "Reduce load or isolate the stack only if deterministic rules support it.",
        ),
        verification_steps=(
            "Confirm the fuel-flow drop is not attributable to a commanded "
            "load reduction before treating it as a supply issue.",
        ),
    ),
    "sensor_anomaly": FaultClassMapping(
        fault_class="sensor_anomaly",
        situation_type="sensor_reading_anomaly",
        relevant_measurements=("stack_temperature", "current", "voltage", "fuel_flow"),
        operator_impact=(
            "A faulty sensor risks masking a real fault or triggering false "
            "alarms; it is not itself an operational safety event."
        ),
        allowed_categories=("investigate", "monitor"),
        recommended_steps=(
            "Compare the suspect measurement against a redundant or manual "
            "reading before taking any other action.",
            "Inspect sensor wiring, connections, and calibration.",
        ),
        verification_steps=(
            "Do not intervene in the plant based solely on the suspect sensor's "
            "own reading.",
        ),
    ),
}


def is_supported_fault_class(fault_class: str) -> bool:
    return fault_class in FAULT_CLASS_MAPPINGS


def get_fault_class_mapping(fault_class: str) -> FaultClassMapping:
    mapping = FAULT_CLASS_MAPPINGS.get(fault_class)
    if mapping is None:
        raise KeyError(f"unsupported fault class: {fault_class!r}")
    return mapping
