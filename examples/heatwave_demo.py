import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application import (
    DecisionPlanner,
    OperationalSituationAssessor,
    TrendDetector,
    create_decision_context,
)
from domain.entities import Asset, Observation, OperationalGoal
from domain.value_objects import Location, MeasurementType

SEPARATOR = "-" * 60


def print_stage(title: str) -> None:
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print()


def format_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%d %H:%M UTC")


def main() -> None:
    asset = Asset(
        id="transformer-t-12",
        name="Transformer T-12",
        type="transformer",
        location=Location(identifier="substation-alpha"),
    )

    goal = OperationalGoal(
        id="goal-grid-stability",
        description="Maintain grid stability during peak demand",
    )

    temperature = MeasurementType(name="temperature")
    base_time = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    readings = (32.0, 36.5, 41.0, 45.5, 50.0)

    observations = tuple(
        Observation(
            id=f"obs-{index}",
            asset_id=asset.id,
            timestamp=base_time + timedelta(hours=index),
            measurement_type=temperature,
            value=value,
            unit="celsius",
        )
        for index, value in enumerate(readings)
    )

    trend = TrendDetector().detect(observations)
    situation = OperationalSituationAssessor().assess(goal, trend, observations)
    context = create_decision_context(goal, situation)
    plan = DecisionPlanner().plan(context)

    print("ODIS Operational Walkthrough")
    print("Scenario: Rising transformer temperature during a heatwave")
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

    print_stage("3. Signal Detection")
    print(f"Trend: {trend.direction.name.title()}")

    print_stage("4. Operational Assessment")
    print(situation.assessment)

    print_stage("5. Decision Context")
    print(f"Goal:       {goal.description}")
    print(f"Assessment: {context.assessment}")

    print_stage("6. Decision Plan")
    print(f"Priority:       {plan.priority.name}")
    print(f"Recommendation: {plan.recommendation}")
    print(f"Justification:  {plan.justification}")
    print()


if __name__ == "__main__":
    main()
