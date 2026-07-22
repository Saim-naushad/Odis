"""Fault-class mapping specification (PR178 spec sections 6, 19 "Mapping").

Every supported ML class maps to exactly one deterministic situation
type; no unsupported classes (including `healthy`) are mapped at all.
"""

from __future__ import annotations

import pytest

from backend.app.application.reasoning_bridge.fault_class_mapping import (
    FAULT_CLASS_MAPPINGS,
    get_fault_class_mapping,
    is_supported_fault_class,
)

_SUPPORTED_CLASSES = (
    "cooling_degradation",
    "hydrogen_supply_issue",
    "sensor_anomaly",
)


@pytest.mark.parametrize("fault_class", _SUPPORTED_CLASSES)
def test_every_supported_class_maps_to_exactly_one_situation_type(
    fault_class: str,
) -> None:
    assert is_supported_fault_class(fault_class)
    mapping = get_fault_class_mapping(fault_class)
    assert mapping.fault_class == fault_class
    assert isinstance(mapping.situation_type, str) and mapping.situation_type


def test_situation_types_are_unique_across_classes() -> None:
    situation_types = [m.situation_type for m in FAULT_CLASS_MAPPINGS.values()]
    assert len(situation_types) == len(set(situation_types))


def test_exactly_three_supported_classes() -> None:
    assert set(FAULT_CLASS_MAPPINGS) == set(_SUPPORTED_CLASSES)


def test_healthy_is_never_a_supported_class() -> None:
    assert not is_supported_fault_class("healthy")


def test_unsupported_class_is_not_mapped() -> None:
    assert not is_supported_fault_class("membrane_dehydration")
    with pytest.raises(KeyError):
        get_fault_class_mapping("membrane_dehydration")


@pytest.mark.parametrize("fault_class", _SUPPORTED_CLASSES)
def test_allowed_categories_never_include_mitigate(fault_class: str) -> None:
    """PR178 never recommends actuator-adjacent "mitigate" actions — only
    "investigate"/"monitor" (spec section 21: no actuator commands)."""
    mapping = get_fault_class_mapping(fault_class)
    assert "mitigate" not in mapping.allowed_categories
    assert set(mapping.allowed_categories) <= {"investigate", "monitor"}


@pytest.mark.parametrize("fault_class", _SUPPORTED_CLASSES)
def test_relevant_measurements_are_non_empty(fault_class: str) -> None:
    mapping = get_fault_class_mapping(fault_class)
    assert len(mapping.relevant_measurements) > 0


def test_sensor_anomaly_recommends_verification_before_intervention() -> None:
    mapping = get_fault_class_mapping("sensor_anomaly")
    all_text = " ".join(mapping.recommended_steps + mapping.verification_steps).lower()
    assert "redundant" in all_text or "manual" in all_text
