from dataclasses import FrozenInstanceError

import pytest

from application.operational_context import OperationalContext
from application.operational_context_builder import OperationalContextBuilder


def test_build_returns_operational_context() -> None:
    context = OperationalContextBuilder().build(
        description="Steady-state operation under increasing load."
    )

    assert isinstance(context, OperationalContext)


def test_build_preserves_optional_arguments() -> None:
    context = OperationalContextBuilder().build(
        description="Steady-state operation under increasing load.",
        operating_mode="steady_state",
        objective="maximize_power",
    )

    assert context.description == "Steady-state operation under increasing load."
    assert context.operating_mode == "steady_state"
    assert context.objective == "maximize_power"


def test_build_defaults_optional_arguments_to_none() -> None:
    context = OperationalContextBuilder().build(
        description="Startup ramp with limited operator intervention."
    )

    assert context.operating_mode is None
    assert context.objective is None


def test_build_is_deterministic() -> None:
    builder = OperationalContextBuilder()

    first = builder.build(
        description="Steady-state operation under increasing load.",
        operating_mode="steady_state",
        objective="maximize_power",
    )
    second = builder.build(
        description="Steady-state operation under increasing load.",
        operating_mode="steady_state",
        objective="maximize_power",
    )

    assert first == second


def test_built_contexts_use_operational_context_equality() -> None:
    builder = OperationalContextBuilder()

    context = builder.build(
        description="Steady-state operation under increasing load.",
        operating_mode="steady_state",
        objective="maximize_power",
    )

    assert context == OperationalContext(
        description="Steady-state operation under increasing load.",
        operating_mode="steady_state",
        objective="maximize_power",
    )


def test_build_preserves_operational_context_immutability() -> None:
    context = OperationalContextBuilder().build(
        description="Steady-state operation under increasing load."
    )

    with pytest.raises(FrozenInstanceError):
        context.description = "Changed"  # type: ignore[misc]
