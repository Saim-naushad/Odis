from datetime import UTC, datetime, timedelta

from application import InMemoryEventPublisher, ReasoningSession
from application.event_publisher import DomainEvent
from application.reasoning_run import ReasoningRun
from application.reasoning_session import ReasoningResult
from domain.entities import Asset, Observation, OperationalGoal
from domain.entities.action import Action
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.outcome import Outcome
from domain.value_objects import Location, MeasurementType
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation

SEPARATOR = "-" * 60


def print_stage(title: str) -> None:
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print()


def format_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%d %H:%M UTC")


def print_reasoning_run(run: ReasoningRun) -> None:
    print()
    print("Reasoning Run")
    print("-------------")
    print(f"Run ID:  {run.id}")
    print(f"Started: {format_timestamp(run.started_at)}")
    print()


def print_signal_detection(trend: DetectedTrend, variation: DetectedVariation) -> None:
    print_stage("3. Signal Detection")
    print("Trend")
    print("------")
    print(trend.direction.name.title())
    print()
    print("Variation")
    print("---------")
    print(variation.level.name)


def print_assessment(assessment: str) -> None:
    print_stage("4. Assessment")
    print(assessment)


def print_decision(plan: DecisionPlan, context: DecisionContext) -> None:
    print_stage("5. Decision")
    print(f"Context:        {context.id}")
    print(f"Priority:       {plan.priority.name}")
    print(f"Recommendation: {plan.recommendation}")
    print(f"Justification:  {plan.justification}")
    print()


def print_action(action: Action) -> None:
    print_stage("6. Action")
    print("Action")
    print("-------")
    print(f"Action ID: {action.id}")
    print(f"Plan ID:   {action.plan_id}")
    print()


def print_outcome(outcome: Outcome) -> None:
    print_stage("7. Outcome")
    print("Outcome")
    print("--------")
    print(f"Outcome ID: {outcome.id}")
    print(f"Action ID:  {outcome.action_id}")
    print()


def main() -> tuple[ReasoningResult, tuple[Observation, ...], tuple[DomainEvent, ...]]:
    asset = Asset(
        id="valve-v-03",
        name="Valve V-03",
        type="control_valve",
        location=Location(identifier="distribution-line-gamma"),
    )

    goal = OperationalGoal(
        id="goal-flow-reliability",
        description="Ensure reliable flow through the distribution line",
    )

    flow_rate = MeasurementType(name="flow_rate")
    base_time = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    readings = (100.0, 150.0, 80.0, 160.0, 70.0, 100.0)

    observations = tuple(
        Observation(
            id=f"obs-{index}",
            asset_id=asset.id,
            timestamp=base_time + timedelta(hours=index),
            measurement_type=flow_rate,
            value=value,
            unit="m3/h",
        )
        for index, value in enumerate(readings)
    )

    publisher = InMemoryEventPublisher()
    result = ReasoningSession(event_publisher=publisher).run(goal, observations)

    print("ODIS Operational Walkthrough")
    print("Scenario: Oscillating flow rate with equal start and end values")
    print(SEPARATOR)

    print_stage("1. Asset")
    print(f"Name:     {asset.name}")
    print(f"Type:     {asset.type}")
    print(f"Location: {asset.location.identifier}")

    print_stage("2. Incoming Observations")
    ordered_observations = sorted(
        observations,
        key=lambda observation: observation.timestamp,
    )
    for observation in ordered_observations:
        print(
            f"{format_timestamp(observation.timestamp)}"
            f"   {observation.value} {observation.unit}"
        )

    print_reasoning_run(result.run)
    print_signal_detection(result.trend, result.variation)
    print_assessment(result.situation.assessment)
    print_decision(result.plan, result.context)
    print_action(result.action)
    print_outcome(result.outcome)

    print(SEPARATOR)
    print("Engineering Observation:")
    print(SEPARATOR)
    print()
    print(
        "Earlier versions of ODIS relied only on trend detection. Multi-signal "
        "reasoning now combines trend and variation to distinguish stable "
        "operation from unstable oscillation."
    )
    print()

    return result, observations, publisher.events


if __name__ == "__main__":
    main()
