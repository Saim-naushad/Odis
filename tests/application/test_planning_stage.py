import pytest

from application.operational_profile import OperationalProfile
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.planning_stage import PlanningStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from domain.value_objects.priority import Priority
from tests.builders import build_goal, build_observation_sequence


def _assessed_context(values: list[float]) -> ReasoningContext:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence(values),
        profile=OperationalProfile.default(),
    )
    for stage in (
        SignalExtractionStage(),
        EvidenceGenerationStage(),
        HypothesisStage(),
        AssessmentStage(),
    ):
        context = stage.run(context)
    return context


def test_planning_stage_requires_assessment() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 20.0]),
        profile=OperationalProfile.default(),
    )

    with pytest.raises(ValueError, match="assessment must be completed"):
        PlanningStage().run(context)


def test_planning_stage_preserves_existing_planner_output() -> None:
    context = PlanningStage().run(
        _assessed_context([32.0, 36.5, 41.0, 45.5, 50.0])
    )
    summary = context.artifacts.assessment_summary
    decision_context = context.artifacts.decision_context
    plan = context.artifacts.decision_plan

    assert summary is not None
    assert summary.situation is not None
    assert decision_context is not None
    assert decision_context.situation_id == summary.situation.id
    assert decision_context.assessment == summary.situation.assessment
    assert plan is not None
    assert plan.context_id == decision_context.id
    assert plan.priority == Priority.HIGH
    assert plan.recommendation == "Investigate operational conditions"
    assert plan.justification == "Operational assessment indicates increasing stress."
    assert context.artifacts.planning_context is not None
    assert context.artifacts.confidence is None
    assert context.artifacts.explanation is None
