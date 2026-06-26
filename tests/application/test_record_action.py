from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import MagicMock, patch

from application.record_action import record_action
from domain.entities.decision_plan import DecisionPlan
from domain.value_objects.priority import Priority
from tests.builders import DEFAULT_TIMESTAMP


def build_plan(**overrides: Any) -> DecisionPlan:
    defaults: dict[str, Any] = {
        "id": "plan-1",
        "context_id": "context-1",
        "created_at": DEFAULT_TIMESTAMP,
        "priority": Priority.LOW,
        "recommendation": "Continue monitoring",
        "justification": "Operational conditions remain stable.",
    }
    defaults.update(overrides)
    return DecisionPlan(
        id=defaults["id"],
        context_id=defaults["context_id"],
        created_at=defaults["created_at"],
        priority=defaults["priority"],
        recommendation=defaults["recommendation"],
        justification=defaults["justification"],
    )


def test_record_action_references_the_supplied_plan() -> None:
    plan = build_plan(id="plan-42")

    action = record_action(plan)

    assert action.plan_id == plan.id


def test_record_action_generates_a_new_id_on_every_call() -> None:
    plan = build_plan()

    first_action = record_action(plan)
    second_action = record_action(plan)

    assert first_action.id != second_action.id


def test_record_action_returns_an_immutable_action() -> None:
    action = record_action(build_plan())

    try:
        action.plan_id = "other-plan"  # type: ignore[misc]
        raise AssertionError("expected Action to be immutable")
    except FrozenInstanceError:
        pass


@patch("application.decision_planner.DecisionPlanner.plan")
def test_record_action_does_not_invoke_the_planner(mock_plan: MagicMock) -> None:
    record_action(build_plan())

    mock_plan.assert_not_called()
