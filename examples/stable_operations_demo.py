import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application import (
    DecisionPlanner,
    OperationalSituationAssessor,
    TrendDetector,
    VariationDetector,
    create_decision_context,
)
from domain.entities import Asset, Observation, OperationalGoal
from domain.entities.decision_plan import DecisionPlan
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


def print_decision(plan: DecisionPlan) -> None:
    print_stage("5. Decision")
    print(f"Priority:       {plan.priority.name}")
    print(f"Recommendation: {plan.recommendation}")
    print(f"Justification:  {plan.justification}")
    print()


def main() -> None:
    asset = Asset(
        id="pump-p-07",
        name="Pump P-07",
        type="centrifugal_pump",
        location=Location(identifier="cooling-loop-beta"),
    )

    goal = OperationalGoal(
        id="goal-process-stability",
        description="Maintain stable process conditions during normal operations",
    )

    pressure = MeasurementType(name="pressure")
    base_time = datetime(2026, 3, 10, 8, 0, tzinfo=UTC)
    readings = (120.0, 120.5, 119.8, 120.2, 120.0)

    observations = tuple(
        Observation(
            id=f"obs-{index}",
            asset_id=asset.id,
            timestamp=base_time + timedelta(hours=index),
            measurement_type=pressure,
            value=value,
            unit="kPa",
        )
        for index, value in enumerate(readings)
    )

    trend = TrendDetector().detect(observations)
    variation = VariationDetector().detect(observations)
    situation = OperationalSituationAssessor().assess(
        goal, observations, trend, variation
    )
    context = create_decision_context(goal, situation)
    plan = DecisionPlanner().plan(context)

    print("ODIS Operational Walkthrough")
    print("Scenario: Stable pump pressure during normal operations")
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

    print_signal_detection(trend, variation)
    print_assessment(situation.assessment)
    print_decision(plan)


if __name__ == "__main__":
    main()
