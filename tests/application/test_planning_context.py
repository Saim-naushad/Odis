from dataclasses import FrozenInstanceError

import pytest

from application.decision_planner import DecisionPlanner
from application.planning_context import PlanningContext
from application.structured_assessment import StructuredAssessment
from domain.entities.decision_context import DecisionContext
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel
from tests.builders import DEFAULT_TIMESTAMP


def _assessment(
    *,
    has_correlations: bool,
    has_contradictions: bool,
) -> StructuredAssessment:
    return StructuredAssessment(
        trend_direction=TrendDirection.STABLE,
        variation_level=VariationLevel.LOW,
        has_correlations=has_correlations,
        has_contradictions=has_contradictions,
    )


def _context(assessment: str) -> DecisionContext:
    return DecisionContext(
        id="context-1",
        goal_id="goal-1",
        situation_id="situation-1",
        assessment=assessment,
        created_at=DEFAULT_TIMESTAMP,
    )


@pytest.mark.parametrize(
    ("has_correlations", "has_contradictions", "expected_has_relationships"),
    [
        (False, False, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
def test_factory_aggregates_relationships(
    has_correlations: bool,
    has_contradictions: bool,
    expected_has_relationships: bool,
) -> None:
    context = PlanningContext.from_assessment(
        _assessment(
            has_correlations=has_correlations,
            has_contradictions=has_contradictions,
        )
    )

    assert context.has_relationships is expected_has_relationships


@pytest.mark.parametrize("has_contradictions", [False, True])
def test_factory_propagates_contradictions(
    has_contradictions: bool,
) -> None:
    context = PlanningContext.from_assessment(
        _assessment(has_correlations=False, has_contradictions=has_contradictions)
    )

    assert context.has_contradictions is has_contradictions


def test_planner_behavior_is_unchanged_when_planning_context_is_present() -> None:
    decision_context = _context("Operational conditions stable")
    planning_context = PlanningContext.from_assessment(
        _assessment(has_correlations=True, has_contradictions=True)
    )

    plan_with_context = DecisionPlanner().plan(
        decision_context, planning_context=planning_context
    )
    plan_without_context = DecisionPlanner().plan(decision_context)

    assert plan_with_context.priority == plan_without_context.priority
    assert plan_with_context.recommendation == plan_without_context.recommendation
    assert plan_with_context.justification == plan_without_context.justification


def test_planning_context_is_immutable() -> None:
    context = PlanningContext.from_assessment(
        _assessment(has_correlations=False, has_contradictions=False)
    )

    with pytest.raises(FrozenInstanceError):
        context.has_relationships = True  # type: ignore[misc]
