from application.reasoning_session import ReasoningSession
from domain.value_objects import Priority, TrendDirection, VariationLevel
from tests.builders import build_goal, build_observation_sequence


def test_reasoning_session_runs_the_operational_pipeline() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])

    result = ReasoningSession().run(goal, observations)

    assert result.trend.direction == TrendDirection.INCREASING
    assert result.variation.level == VariationLevel.LOW
    assert result.situation.assessment == "Increasing operational stress detected"
    assert result.context.assessment == result.situation.assessment
    assert result.context.situation_id == result.situation.id
    assert result.plan.context_id == result.context.id
    assert result.plan.priority == Priority.HIGH
    assert result.plan.recommendation == "Investigate operational conditions"
