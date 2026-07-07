from __future__ import annotations

from datetime import UTC, datetime, timedelta

from application.observation_pipeline import ObservationPipeline
from application.planning_context import PlanningContext
from application.profiles.fuel_cell_profile import FuelCellOperationalProfile
from application.reasoning_session import ReasoningResult, ReasoningSession
from application.relationship_analysis import RelationshipAnalyzer
from application.structured_assessment import StructuredAssessment
from domain.entities import Asset, Observation, OperationalGoal
from domain.entities.action import Action
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.outcome import Outcome
from domain.value_objects import Location, MeasurementType
from infrastructure.sources import StaticObservationSource
from odis.examples.heatwave_demo import format_timestamp, print_stage

SEPARATOR = "-" * 60


def _print_profile_name(profile: FuelCellOperationalProfile) -> None:
    print_stage("0. Domain Profile")
    print(f"Profile: {profile.__class__.__name__}")


def _print_observations(observations: tuple[Observation, ...]) -> None:
    print_stage("1. Incoming Observations")
    ordered = sorted(observations, key=lambda observation: observation.timestamp)
    for observation in ordered:
        print(
            f"{format_timestamp(observation.timestamp)}"
            f"   {observation.measurement_type.name}"
            f"   {observation.value} {observation.unit}"
        )


def _print_structured_assessment(assessment: StructuredAssessment) -> None:
    print_stage("2. Structured Assessment")
    print(f"Trend direction:     {assessment.trend_direction.name}")
    print(f"Variation level:     {assessment.variation_level.name}")
    print(f"Has correlations:    {assessment.has_correlations}")
    print(f"Has contradictions:  {assessment.has_contradictions}")


def _print_planning_context(context: PlanningContext) -> None:
    print_stage("3. Planning Context")
    print(f"Has relationships:   {context.has_relationships}")
    print(f"Has contradictions:  {context.has_contradictions}")


def _print_decision(plan: DecisionPlan, context: DecisionContext) -> None:
    print_stage("4. Decision Plan")
    print(f"Context:        {context.id}")
    print(f"Priority:       {plan.priority.name}")
    print(f"Recommendation: {plan.recommendation}")
    print(f"Justification:  {plan.justification}")


def _print_action(action: Action) -> None:
    print_stage("5. Action")
    print(f"Action ID: {action.id}")
    print(f"Plan ID:   {action.plan_id}")


def _print_outcome(outcome: Outcome) -> None:
    print_stage("6. Outcome")
    print(f"Outcome ID: {outcome.id}")
    print(f"Action ID:  {outcome.action_id}")


def main() -> tuple[ReasoningResult, tuple[Observation, ...]]:
    profile = FuelCellOperationalProfile.default()

    asset = Asset(
        id="fuel-cell-stack-01",
        name="Fuel Cell Stack 01",
        type="fuel_cell_stack",
        location=Location(identifier="lab-bay-1"),
    )
    goal = OperationalGoal(
        id="goal-stable-generation",
        description="Maintain stable electrical generation from the fuel cell stack",
    )

    base_time = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)

    stack_temperature = MeasurementType(name="stack_temperature")
    stack_pressure = MeasurementType(name="stack_pressure")
    current = MeasurementType(name="current")
    voltage = MeasurementType(name="voltage")
    fuel_flow = MeasurementType(name="fuel_flow")

    temperature_readings = (62.0, 64.0, 66.0, 68.0, 70.0)
    pressure_readings = (155.0, 153.5, 152.0, 150.5, 149.0)
    current_readings = (120.0, 130.0, 140.0, 150.0, 160.0)
    voltage_readings = (0.78, 0.77, 0.76, 0.75, 0.74)
    fuel_flow_readings = (1.9, 2.0, 2.1, 2.1, 2.2)

    def build_series(
        measurement: MeasurementType,
        values: tuple[float, ...],
        *,
        unit: str,
        id_prefix: str,
    ) -> tuple[Observation, ...]:
        return tuple(
            Observation(
                id=f"{id_prefix}-{index}",
                asset_id=asset.id,
                timestamp=base_time + timedelta(minutes=5 * index),
                measurement_type=measurement,
                value=value,
                unit=unit,
            )
            for index, value in enumerate(values)
        )

    observations = (
        *build_series(
            stack_temperature,
            temperature_readings,
            unit="celsius",
            id_prefix="temp",
        ),
        *build_series(
            stack_pressure,
            pressure_readings,
            unit="kPa",
            id_prefix="pressure",
        ),
        *build_series(
            current,
            current_readings,
            unit="A",
            id_prefix="current",
        ),
        *build_series(
            voltage,
            voltage_readings,
            unit="V",
            id_prefix="voltage",
        ),
        *build_series(
            fuel_flow,
            fuel_flow_readings,
            unit="SLPM",
            id_prefix="fuel",
        ),
    )

    reasoning_observations = tuple(
        observation
        for observation in observations
        if observation.measurement_type == stack_temperature
    )

    pipeline = ObservationPipeline(session=ReasoningSession(profile=profile))
    result = pipeline.process(goal, StaticObservationSource(reasoning_observations))

    group = pipeline.group(tuple(observations))
    relationship_analysis = RelationshipAnalyzer(profile=profile).analyze(group)
    structured = StructuredAssessment.from_reasoning(
        result.trend,
        result.variation,
        relationship_analysis=relationship_analysis,
    )
    planning_context = PlanningContext.from_assessment(structured)

    print("ODIS Operational Walkthrough")
    print("Scenario: Fuel cell profile demonstration")
    print(SEPARATOR)

    _print_profile_name(profile)
    _print_observations(tuple(observations))
    _print_structured_assessment(structured)
    _print_planning_context(planning_context)
    _print_decision(result.plan, result.context)
    _print_action(result.action)
    _print_outcome(result.outcome)

    return result, tuple(observations)


if __name__ == "__main__":
    main()

