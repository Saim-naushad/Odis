from application import (
    DecisionPlanner,
    OperationalSituationAssessor,
    TrendDetector,
    create_decision_context,
)
from domain.value_objects import Priority, TrendDirection
from domain.value_objects.location import Location
from tests.builders import build_asset, build_goal, build_observation_sequence


def test_heatwave_scenario_produces_increasing_operational_response() -> None:
    asset = build_asset(
        id="transformer-t-12",
        name="Transformer T-12",
        type="transformer",
        location=Location(identifier="substation-alpha"),
    )
    goal = build_goal(
        id="goal-grid-stability",
        description="Maintain grid stability during peak demand",
    )
    observations = build_observation_sequence(
        [32.0, 36.5, 41.0, 45.5, 50.0],
        asset_id=asset.id,
        unit="celsius",
    )

    trend = TrendDetector().detect(observations)
    situation = OperationalSituationAssessor().assess(goal, trend, observations)
    context = create_decision_context(goal, situation)
    plan = DecisionPlanner().plan(context)

    assert trend.direction == TrendDirection.INCREASING
    assert situation.assessment == "Increasing operational stress detected"
    assert plan.priority == Priority.HIGH
    assert plan.recommendation == "Investigate operational conditions"
    assert plan.justification == (
        "Operational assessment indicates increasing stress."
    )
