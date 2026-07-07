from application.contradiction_detector import OperationalContradiction
from application.correlation_detector import MeasurementCorrelation
from application.expectation import Expectation
from application.expectation_evaluator import ExpectationEvaluator
from application.fuel_cell_expectation_evaluator import FuelCellExpectationEvaluator
from application.relationship_analysis import RelationshipAnalysis
from domain.value_objects.measurement_type import MeasurementType


def _expectation(
    *,
    name: str = "Cooling tracks load",
    description: str = "Coolant flow should increase with electrical load.",
) -> Expectation:
    return Expectation(name=name, description=description)


def _correlation() -> MeasurementCorrelation:
    return MeasurementCorrelation(
        measurement_a=MeasurementType(name="current"),
        measurement_b=MeasurementType(name="voltage"),
        relationship="Example correlation",
    )


def _contradiction() -> OperationalContradiction:
    return OperationalContradiction(description="Example contradiction")


def test_evaluate_relationship_returns_expected_when_correlations_exist() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()
    relationships = RelationshipAnalysis(
        correlations=(_correlation(),),
        contradictions=(),
    )

    evaluation = evaluator.evaluate_relationship(expectation, relationships)

    assert evaluation.expectation == expectation
    assert evaluation.status == "expected"
    assert (
        evaluation.explanation
        == "The observed behavior matches this engineering expectation."
    )


def test_evaluate_relationship_returns_unexpected_when_only_contradictions() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()
    relationships = RelationshipAnalysis(
        correlations=(),
        contradictions=(_contradiction(),),
    )

    evaluation = evaluator.evaluate_relationship(expectation, relationships)

    assert evaluation.expectation == expectation
    assert evaluation.status == "unexpected"
    assert (
        evaluation.explanation
        == "The observed behavior diverges from this engineering expectation."
    )


def test_evaluate_relationship_returns_indeterminate_when_no_evidence_exists() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()
    relationships = RelationshipAnalysis(correlations=(), contradictions=())

    evaluation = evaluator.evaluate_relationship(expectation, relationships)

    assert evaluation.expectation == expectation
    assert evaluation.status == "indeterminate"
    assert (
        evaluation.explanation
        == "Insufficient evidence is available to evaluate this expectation."
    )


def test_evaluate_relationship_delegates_to_expectation_evaluator() -> None:
    expectation = _expectation()
    profile_evaluator = FuelCellExpectationEvaluator()
    generic_evaluator = ExpectationEvaluator()
    cases = (
        (
            RelationshipAnalysis(correlations=(_correlation(),), contradictions=()),
            True,
        ),
        (
            RelationshipAnalysis(
                correlations=(),
                contradictions=(_contradiction(),),
            ),
            False,
        ),
        (RelationshipAnalysis(correlations=(), contradictions=()), None),
    )

    for relationships, satisfied in cases:
        profile_result = profile_evaluator.evaluate_relationship(
            expectation,
            relationships,
        )
        generic_result = generic_evaluator.evaluate(
            expectation,
            satisfied=satisfied,
        )

        assert profile_result == generic_result


def test_evaluate_relationship_is_deterministic() -> None:
    expectation = _expectation()
    evaluator = FuelCellExpectationEvaluator()
    cases = (
        RelationshipAnalysis(correlations=(_correlation(),), contradictions=()),
        RelationshipAnalysis(correlations=(), contradictions=(_contradiction(),)),
        RelationshipAnalysis(correlations=(), contradictions=()),
    )

    for relationships in cases:
        first = evaluator.evaluate_relationship(expectation, relationships)
        second = evaluator.evaluate_relationship(expectation, relationships)

        assert first == second
