from __future__ import annotations

from application.hypothesis import Hypothesis
from application.hypothesis_refiner import HypothesisRefiner
from application.operational_state import OperationalState


def _hypothesis(*, name: str, rationale: str) -> Hypothesis:
    return Hypothesis(
        operational_state=OperationalState(
            name=name,
            description=f"Operational state description for {name}.",
        ),
        rationale=rationale,
    )


def test_refine_empty_input_returns_empty_tuple() -> None:
    refiner = HypothesisRefiner()

    assert refiner.refine([], lambda _: True) == ()


def test_refine_all_survive() -> None:
    refiner = HypothesisRefiner()
    hypotheses = (
        _hypothesis(name="A", rationale="keep"),
        _hypothesis(name="B", rationale="keep"),
    )

    survivors = refiner.refine(hypotheses, lambda _: True)

    assert survivors == hypotheses
    assert isinstance(survivors, tuple)


def test_refine_all_eliminated() -> None:
    refiner = HypothesisRefiner()
    hypotheses = (
        _hypothesis(name="A", rationale="drop"),
        _hypothesis(name="B", rationale="drop"),
    )

    assert refiner.refine(hypotheses, lambda _: False) == ()


def test_refine_partial_elimination() -> None:
    refiner = HypothesisRefiner()
    first = _hypothesis(name="A", rationale="keep")
    second = _hypothesis(name="B", rationale="drop")
    third = _hypothesis(name="C", rationale="keep")
    hypotheses = (first, second, third)

    survivors = refiner.refine(hypotheses, lambda h: h.rationale == "keep")

    assert survivors == (first, third)


def test_refine_preserves_original_ordering() -> None:
    refiner = HypothesisRefiner()
    first = _hypothesis(name="A", rationale="keep")
    second = _hypothesis(name="B", rationale="keep")
    third = _hypothesis(name="C", rationale="keep")
    hypotheses = (first, second, third)

    survivors = refiner.refine(hypotheses, lambda h: h.operational_state.name != "B")

    assert survivors == (first, third)


def test_refine_is_deterministic_across_repeated_execution() -> None:
    refiner = HypothesisRefiner()
    hypotheses = (
        _hypothesis(name="A", rationale="keep"),
        _hypothesis(name="B", rationale="drop"),
        _hypothesis(name="C", rationale="keep"),
    )

    def predicate(hypothesis: Hypothesis) -> bool:
        return hypothesis.rationale == "keep"

    first_run = refiner.refine(hypotheses, predicate)
    second_run = refiner.refine(hypotheses, predicate)

    assert first_run == second_run


def test_refine_does_not_modify_input_collection() -> None:
    refiner = HypothesisRefiner()
    hypothesis_list = [
        _hypothesis(name="A", rationale="keep"),
        _hypothesis(name="B", rationale="drop"),
    ]
    original_snapshot = list(hypothesis_list)

    survivors = refiner.refine(hypothesis_list, lambda h: h.rationale == "keep")

    assert hypothesis_list == original_snapshot
    assert survivors == (hypothesis_list[0],)

