import pytest

from application.decision_planner import DecisionPlanner
from domain.entities.decision_context import DecisionContext
from domain.value_objects.priority import Priority
from tests.builders import DEFAULT_TIMESTAMP


def _context(assessment: str) -> DecisionContext:
    return DecisionContext(
        id="context-1",
        goal_id="goal-1",
        situation_id="situation-1",
        assessment=assessment,
        created_at=DEFAULT_TIMESTAMP,
    )


@pytest.mark.parametrize(
    ("assessment", "priority", "recommendation", "justification"),
    [
        (
            "Increasing operational stress detected",
            Priority.HIGH,
            "Investigate operational conditions",
            "Operational assessment indicates increasing stress.",
        ),
        (
            "Rapidly increasing unstable operational conditions detected",
            Priority.HIGH,
            "Investigate operational conditions",
            "Operational assessment indicates increasing stress.",
        ),
        (
            "Operational conditions stable",
            Priority.LOW,
            "Continue monitoring",
            "Operational conditions remain stable.",
        ),
        (
            "Highly unstable operating conditions detected",
            Priority.HIGH,
            "Investigate operational conditions",
            "Operational assessment indicates unstable conditions.",
        ),
        (
            "Operational conditions improving",
            Priority.LOW,
            "Maintain current operations",
            "Operational conditions are improving.",
        ),
        (
            "Operational conditions remain unstable despite improvement",
            Priority.HIGH,
            "Investigate operational conditions",
            "Operational assessment indicates unstable conditions.",
        ),
    ],
)
def test_planner_maps_assessment_strings_to_expected_outcomes(
    assessment: str,
    priority: Priority,
    recommendation: str,
    justification: str,
) -> None:
    plan = DecisionPlanner().plan(_context(assessment))

    assert plan.priority == priority
    assert plan.recommendation == recommendation
    assert plan.justification == justification


def test_unstable_assessment_does_not_match_stable_rule() -> None:
    plan = DecisionPlanner().plan(
        _context("Highly unstable operating conditions detected")
    )

    assert plan.recommendation != "Continue monitoring"
