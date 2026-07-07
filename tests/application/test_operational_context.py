from dataclasses import FrozenInstanceError

import pytest

from application.operational_context import OperationalContext


def _context(
    *,
    description: str = "Steady-state operation under increasing load.",
    operating_mode: str | None = "steady_state",
    objective: str | None = "maximize_power",
) -> OperationalContext:
    return OperationalContext(
        description=description,
        operating_mode=operating_mode,
        objective=objective,
    )


def test_identical_contexts_compare_equal() -> None:
    first = _context()
    second = _context()

    assert first == second


def test_unequal_contexts_do_not_compare_equal() -> None:
    baseline = _context()

    assert baseline != _context(description="Startup ramp in progress.")
    assert baseline != _context(operating_mode="startup")
    assert baseline != _context(objective="minimize_degradation")


def test_context_is_immutable() -> None:
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.description = "Changed"  # type: ignore[misc]


def test_context_is_hashable() -> None:
    first = _context()
    second = _context()

    assert hash(first) == hash(second)
    assert {first, second} == {_context()}


def test_context_repr_is_readable() -> None:
    context = _context()

    repr_text = repr(context)

    assert "OperationalContext" in repr_text
    assert "Steady-state operation under increasing load." in repr_text
    assert "steady_state" in repr_text
    assert "maximize_power" in repr_text


def test_optional_fields_accept_none() -> None:
    context = _context(operating_mode=None, objective=None)

    assert context.operating_mode is None
    assert context.objective is None
    assert context == _context(operating_mode=None, objective=None)
