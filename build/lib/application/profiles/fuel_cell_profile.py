from __future__ import annotations

from application.expectation import Expectation
from application.expectation_analysis import ExpectationAnalysis
from application.fuel_cell_expectation_evaluator import FuelCellExpectationEvaluator
from application.operational_context import OperationalContext
from application.operational_profile import OperationalProfile
from application.relationship_analysis import RelationshipAnalysis
from application.relationship_policy import RelationshipPolicy, RelationshipRule
from domain.value_objects.measurement_type import MeasurementType


class FuelCellRelationshipPolicy(RelationshipPolicy):
    """Representative relationships for a fuel-cell stack.

    These rules are intentionally illustrative and deterministic. They encode
    which measurement pairs ODIS should evaluate, without introducing physics or
    changing any detector logic.
    """

    def __init__(self) -> None:
        self._stack_temperature = MeasurementType(name="stack_temperature")
        self._stack_pressure = MeasurementType(name="stack_pressure")
        self._current = MeasurementType(name="current")
        self._voltage = MeasurementType(name="voltage")
        self._fuel_flow = MeasurementType(name="fuel_flow")

    def correlation_rules(self) -> tuple[RelationshipRule, ...]:
        return (
            RelationshipRule(
                measurement_a=self._stack_temperature,
                measurement_b=self._stack_pressure,
            ),
            RelationshipRule(
                measurement_a=self._current,
                measurement_b=self._voltage,
            ),
            RelationshipRule(
                measurement_a=self._fuel_flow,
                measurement_b=self._stack_temperature,
            ),
        )

    def contradiction_rules(self) -> tuple[RelationshipRule, ...]:
        # Keep the first fuel-cell profile focused on correlation evaluation.
        return ()


class FuelCellOperationalProfile(OperationalProfile):
    """Operational profile demonstrating representative fuel-cell relationships.

    Uses composition: the profile simply packages a relationship policy instance
    without redesigning the framework or detectors.
    """

    @classmethod
    def default(cls) -> FuelCellOperationalProfile:
        return cls(relationship_policy=FuelCellRelationshipPolicy())

    def evaluate_expectations(
        self,
        operational_context: OperationalContext,
        relationship_analysis: RelationshipAnalysis,
    ) -> ExpectationAnalysis:
        _ = operational_context
        expectation = Expectation(
            name="Coupled subsystem response",
            description=(
                "Under changing load, correlated measurement trends indicate "
                "coherent fuel-cell subsystem response."
            ),
        )
        evaluation = FuelCellExpectationEvaluator().evaluate_relationship(
            expectation,
            relationship_analysis,
        )
        return ExpectationAnalysis(evaluations=(evaluation,))

