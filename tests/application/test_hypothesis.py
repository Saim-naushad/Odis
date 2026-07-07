from dataclasses import FrozenInstanceError

import pytest

from application.hypothesis import Hypothesis
from application.operational_state import OperationalState


def _hypothesis(
    *,
    operational_state: OperationalState | None = None,
    rationale: str = (
        "Rising temperature, stable load, and declining voltage are consistent with "
        "flooding indicators."
    ),
) -> Hypothesis:
    return Hypothesis(
        operational_state=operational_state
        or OperationalState(
            name="Possible Flooding",
            description=(
                "Evidence suggests liquid water may be accumulating in the stack."
            ),
        ),
        rationale=rationale,
    )


def test_identical_hypotheses_compare_equal() -> None:
    first = _hypothesis()
    second = _hypothesis()

    assert first == second


def test_unequal_hypotheses_do_not_compare_equal() -> None:
    baseline = _hypothesis()

    assert baseline != _hypothesis(
        operational_state=OperationalState(
            name="Possible Membrane Drying",
            description="Evidence suggests the membrane may be losing hydration.",
        )
    )
    assert baseline != _hypothesis(rationale="A different rationale.")


def test_hypothesis_is_immutable() -> None:
    hypothesis = _hypothesis()

    with pytest.raises(FrozenInstanceError):
        hypothesis.rationale = "Changed"  # type: ignore[misc]


def test_hypothesis_is_hashable() -> None:
    first = _hypothesis()
    second = _hypothesis()

    assert hash(first) == hash(second)
    assert {first, second} == {_hypothesis()}


def test_hypothesis_repr_is_readable() -> None:
    hypothesis = _hypothesis()

    repr_text = repr(hypothesis)

    assert "Hypothesis" in repr_text
    assert "Possible Flooding" in repr_text
    assert "Rising temperature, stable load, and declining voltage" in repr_text


def test_identical_value_instances_compare_equal() -> None:
    state = OperationalState(
        name="Normal Operation",
        description="Telemetry and expectations align with steady operation.",
    )
    rationale = "Evidence supports a stable, expected operating condition."

    first = Hypothesis(operational_state=state, rationale=rationale)
    second = Hypothesis(operational_state=state, rationale=rationale)

    assert first == second
    assert hash(first) == hash(second)
