from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

from application.record_action import record_action
from application.record_outcome import record_outcome
from tests.application.test_record_action import build_plan


def test_record_outcome_references_the_supplied_action() -> None:
    action = record_action(build_plan(id="plan-42"))

    outcome = record_outcome(action)

    assert outcome.action_id == action.id


def test_record_outcome_generates_a_new_id_on_every_call() -> None:
    action = record_action(build_plan())

    first_outcome = record_outcome(action)
    second_outcome = record_outcome(action)

    assert first_outcome.id != second_outcome.id


def test_record_outcome_returns_an_immutable_outcome() -> None:
    outcome = record_outcome(record_action(build_plan()))

    try:
        outcome.action_id = "other-action"  # type: ignore[misc]
        raise AssertionError("expected Outcome to be immutable")
    except FrozenInstanceError:
        pass


@patch("application.trend_detector.TrendDetector.detect")
@patch("application.variation_detector.VariationDetector.detect")
@patch("application.decision_planner.DecisionPlanner.plan")
def test_record_outcome_does_not_invoke_planners_or_detectors(
    mock_plan: MagicMock,
    mock_variation_detector: MagicMock,
    mock_trend_detector: MagicMock,
) -> None:
    record_outcome(record_action(build_plan()))

    mock_plan.assert_not_called()
    mock_variation_detector.assert_not_called()
    mock_trend_detector.assert_not_called()
