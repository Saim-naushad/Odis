from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from application.create_decision_context import create_decision_context
from application.decision_planner import DecisionPlanner
from application.event_publisher import InMemoryEventPublisher
from application.expectation_analysis import ExpectationAnalysis
from application.operational_context import OperationalContext
from application.operational_profile import OperationalProfile
from application.operational_situation_assessor import OperationalSituationAssessor
from application.planning_context import PlanningContext
from application.profiles.fuel_cell_profile import FuelCellOperationalProfile
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_session import ReasoningSession
from application.relationship_analysis import RelationshipAnalysis
from domain.events.decision_context_created import DecisionContextCreated
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from domain.events.operational_situation_created import OperationalSituationCreated
from domain.value_objects import Priority, TrendDirection, VariationLevel
from domain.value_objects.measurement_type import MeasurementType
from infrastructure.repositories.decision_context_repository import (
    InMemoryDecisionContextRepository,
)
from infrastructure.repositories.decision_plan_repository import (
    InMemoryDecisionPlanRepository,
)
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from infrastructure.repositories.reasoning_run_index_repository import (
    InMemoryReasoningRunIndexRepository,
)
from infrastructure.repositories.reasoning_run_registry_repository import (
    InMemoryReasoningRunRegistryRepository,
)
from infrastructure.repositories.reasoning_run_repository import (
    InMemoryReasoningRunRepository,
)
from infrastructure.repositories.situation_repository import InMemorySituationRepository
from tests.builders import build_goal, build_observation, build_observation_sequence


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
    assert result.action.plan_id == result.plan.id
    assert result.outcome.action_id == result.action.id
    assert result.run.id
    assert result.run.started_at.tzinfo is not None
    assert result.operational_context == OperationalContext(
        description="Operational reasoning context",
        operating_mode=None,
        objective=None,
    )
    assert isinstance(result.expectation_analysis, ExpectationAnalysis)
    assert result.expectation_analysis.expected_count == 0
    assert result.expectation_analysis.unexpected_count == 0
    assert result.expectation_analysis.indeterminate_count == 0
    assert result.expectation_analysis.has_unexpected is False
    assert result.expectation_analysis.has_indeterminate is False
    assert result.structured_assessment.trend_direction == result.trend.direction
    assert result.structured_assessment.variation_level == result.variation.level
    assert result.planning_context == PlanningContext.from_assessment(
        result.structured_assessment
    )
    artifacts = result.reasoning_context.artifacts
    assert artifacts.signals is not None
    assert artifacts.evidence
    assert artifacts.hypotheses
    assert artifacts.assessment_summary is not None
    assert artifacts.structured_assessment == result.structured_assessment
    assert artifacts.decision_context == result.context
    assert artifacts.decision_plan == result.plan
    assert artifacts.confidence is not None
    assert artifacts.explanation is not None
    assert artifacts.assessment_summary is not None
    assert artifacts.assessment_summary.confidence == artifacts.confidence


def test_reasoning_session_owns_explicit_ordered_stages() -> None:
    session = ReasoningSession()

    assert tuple(stage.name for stage in session.stages) == (
        "Signal Extraction",
        "Evidence Generation",
        "Hypothesis Generation",
        "Assessment",
        "Confidence",
        "Explanation",
        "Planning",
    )


@pytest.mark.parametrize(
    "values",
    [
        [10.0, 20.0, 30.0],
        [20.0, 20.0, 20.0],
        [30.0, 20.0, 10.0],
        [10.0, 30.0, 5.0, 40.0],
    ],
)
def test_explicit_pipeline_preserves_assessment_and_planning_outputs(
    values: list[float],
) -> None:
    goal = build_goal()
    observations = build_observation_sequence(values)

    result = ReasoningSession().run(goal, observations)
    signals = result.reasoning_context.artifacts.signals
    assert signals is not None

    legacy_assessment = OperationalSituationAssessor().assess(
        goal,
        signals.primary_observations,
        signals.trend,
        signals.variation,
        relationship_analysis=signals.relationship_analysis,
        expectation_analysis=signals.expectation_analysis,
    )
    legacy_context = create_decision_context(goal, legacy_assessment.situation)
    legacy_plan = DecisionPlanner().plan(
        legacy_context,
        planning_context=PlanningContext.from_assessment(
            legacy_assessment.structured
        ),
    )

    assert result.situation.assessment == legacy_assessment.situation.assessment
    assert result.structured_assessment == legacy_assessment.structured
    assert result.plan.priority == legacy_plan.priority
    assert result.plan.recommendation == legacy_plan.recommendation
    assert result.plan.justification == legacy_plan.justification


def test_reasoning_session_evaluates_fuel_cell_profile_expectations() -> None:
    profile = FuelCellOperationalProfile.default()
    goal = build_goal()
    temperature = MeasurementType(name="stack_temperature")
    observations = (
        *build_observation_sequence([62.0, 64.0, 66.0], measurement_type=temperature),
        *(
            build_observation(
                value=value,
                measurement_type=MeasurementType(name="stack_pressure"),
                id=f"pressure-{index}",
            )
            for index, value in enumerate([155.0, 153.0, 151.0])
        ),
    )

    result = ReasoningSession(profile=profile).run(goal, observations)

    assert result.structured_assessment.has_correlations is True
    assert result.expectation_analysis.expected_count == 1
    assert result.structured_assessment.has_unexpected_expectations is False


def test_reasoning_session_performs_relationship_analysis() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    with patch(
        "application.reasoning.signal_extraction_stage.RelationshipAnalyzer.analyze",
    ) as analyze_mock:
        analyze_mock.return_value = RelationshipAnalysis(
            correlations=(),
            contradictions=(),
        )
        ReasoningSession().run(goal, observations)

    analyze_mock.assert_called_once()


def test_expectation_evaluation_consumes_operational_context() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    session = ReasoningSession(profile=OperationalProfile.default())
    calls: list[tuple[object, object]] = []
    original_evaluate = OperationalProfile.evaluate_expectations

    def tracking_evaluate(
        self: OperationalProfile,
        operational_context: object,
        relationship_analysis: object,
    ) -> object:
        calls.append((operational_context, relationship_analysis))
        return original_evaluate(self, operational_context, relationship_analysis)

    with patch.object(
        OperationalProfile,
        "evaluate_expectations",
        tracking_evaluate,
    ):
        result = session.run(goal, observations)

    assert len(calls) == 1
    operational_context, relationship_analysis = calls[0]
    assert operational_context is result.operational_context
    assert operational_context.description == "Operational reasoning context"
    assert relationship_analysis.correlations == ()
    assert relationship_analysis.contradictions == ()


def test_each_call_creates_a_unique_run_id() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    first_result = ReasoningSession().run(goal, observations)
    second_result = ReasoningSession().run(goal, observations)

    assert first_result.run.id != second_result.run.id


def test_reasoning_result_preserves_the_run_for_the_execution() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert isinstance(result.run, ReasoningRun)
    assert result.run.started_at <= result.context.created_at
    assert result.run.started_at <= result.plan.created_at


def test_reasoning_session_without_repositories_does_not_persist() -> None:
    goal = build_goal()
    observations = build_observation_sequence([120.0, 120.5, 119.8, 120.2, 120.0])

    result = ReasoningSession().run(goal, observations)

    assert result.situation.assessment == "Operational conditions stable"
    assert result.plan.recommendation == "Continue monitoring"


def test_reasoning_session_with_repositories_persists_every_artifact() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()

    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
    ).run(goal, observations)

    for observation in observations:
        assert observation_repository.get(observation.id) is observation

    assert situation_repository.get(result.situation.id) is result.situation
    assert decision_context_repository.get(result.context.id) is result.context
    assert decision_plan_repository.get(result.plan.id) is result.plan


def test_duplicate_id_causes_the_session_to_fail() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    observation_repository = InMemoryObservationRepository()
    session = ReasoningSession(observation_repository=observation_repository)

    session.run(goal, observations)

    with pytest.raises(ValueError, match="already exists"):
        session.run(goal, observations)


def test_previously_saved_observation_aborts_before_reasoning_completes() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    observation_repository.save(observations[0])

    with pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            observation_repository=observation_repository,
            situation_repository=situation_repository,
        ).run(goal, observations)

    fresh_observations = build_observation_sequence(
        [120.0, 120.5, 120.0],
        id_prefix="fresh",
    )
    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
    ).run(goal, fresh_observations)

    assert situation_repository.get(result.situation.id) is result.situation


def test_reasoning_session_without_publisher_still_works() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.trend.direction == TrendDirection.INCREASING


def test_reasoning_session_emits_events_in_pipeline_order() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    publisher = InMemoryEventPublisher()

    result = ReasoningSession(event_publisher=publisher).run(goal, observations)

    assert len(publisher.events) == len(observations) + 3
    for index, observation in enumerate(observations):
        event = publisher.events[index]
        assert isinstance(event, ObservationRecorded)
        assert event.observation_id == observation.id
        assert event.recorded_at == observation.timestamp

    situation_event = publisher.events[len(observations)]
    assert isinstance(situation_event, OperationalSituationCreated)
    assert situation_event.situation_id == result.situation.id

    context_event = publisher.events[len(observations) + 1]
    assert isinstance(context_event, DecisionContextCreated)
    assert context_event.context_id == result.context.id
    assert context_event.created_at == result.context.created_at

    plan_event = publisher.events[len(observations) + 2]
    assert isinstance(plan_event, DecisionPlanGenerated)
    assert plan_event.plan_id == result.plan.id
    assert plan_event.generated_at == result.plan.created_at


def test_persistence_and_publishing_work_together() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    observation_repository = InMemoryObservationRepository()
    situation_repository = InMemorySituationRepository()
    decision_context_repository = InMemoryDecisionContextRepository()
    decision_plan_repository = InMemoryDecisionPlanRepository()

    result = ReasoningSession(
        observation_repository=observation_repository,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        event_publisher=publisher,
    ).run(goal, observations)

    assert len(publisher.events) == len(observations) + 3
    assert observation_repository.get(observations[0].id) is observations[0]
    assert decision_plan_repository.get(result.plan.id) is result.plan


def test_persistence_failure_aborts_session_without_later_events() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    publisher = InMemoryEventPublisher()
    observation_repository = InMemoryObservationRepository()
    observation_repository.save(observations[0])

    with pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            observation_repository=observation_repository,
            event_publisher=publisher,
        ).run(goal, observations)

    assert len(publisher.events) == 1
    assert isinstance(publisher.events[0], ObservationRecorded)
    assert publisher.events[0].observation_id == observations[0].id


def test_reasoning_session_records_the_full_operational_lifecycle() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.plan.context_id == result.context.id
    assert result.action.plan_id == result.plan.id
    assert result.outcome.action_id == result.action.id
    assert result.action.id != result.plan.id
    assert result.outcome.id != result.action.id


def test_reasoning_session_persists_the_run_when_configured() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_repository = InMemoryReasoningRunRepository()

    result = ReasoningSession(
        reasoning_run_repository=reasoning_run_repository,
    ).run(goal, observations)

    assert reasoning_run_repository.get(result.run.id) is result.run


def test_duplicate_run_id_propagates_failure() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_repository = InMemoryReasoningRunRepository()
    existing_run = ReasoningRun(
        id="fixed-run-id",
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    reasoning_run_repository.save(existing_run)

    with patch(
        "application.reasoning_session.uuid4",
        return_value=existing_run.id,
    ), pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            reasoning_run_repository=reasoning_run_repository,
        ).run(goal, observations)


def test_reasoning_session_without_run_repository_does_not_persist_run() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    observation_repository = InMemoryObservationRepository()

    result = ReasoningSession(
        observation_repository=observation_repository,
    ).run(goal, observations)

    assert result.run.id
    assert observation_repository.get(observations[0].id) is observations[0]


def test_reasoning_session_persists_run_index_when_configured() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()

    result = ReasoningSession(
        reasoning_run_index_repository=reasoning_run_index_repository,
    ).run(goal, observations)

    index = reasoning_run_index_repository.get(result.run.id)

    assert index is not None
    assert index.run_id == result.run.id
    assert index.observation_ids == tuple(
        observation.id for observation in observations
    )
    assert index.situation_id == result.situation.id
    assert index.context_id == result.context.id
    assert index.plan_id == result.plan.id
    assert index.action_id == result.action.id
    assert index.outcome_id == result.outcome.id


def test_duplicate_run_index_propagates_failure() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_index_repository = InMemoryReasoningRunIndexRepository()
    existing_index = ReasoningRunIndex(
        run_id="fixed-run-id",
        observation_ids=("obs-existing",),
        situation_id="situation-existing",
        context_id="context-existing",
        plan_id="plan-existing",
        action_id="action-existing",
        outcome_id="outcome-existing",
    )
    reasoning_run_index_repository.save(existing_index)

    with patch(
        "application.reasoning_session.uuid4",
        return_value=existing_index.run_id,
    ), pytest.raises(ValueError, match="already exists"):
        ReasoningSession(
            reasoning_run_index_repository=reasoning_run_index_repository,
        ).run(goal, observations)


def test_reasoning_session_without_index_repository_is_unchanged() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.situation.assessment == "Increasing operational stress detected"


def test_reasoning_session_registers_the_run_when_configured() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_registry_repository = InMemoryReasoningRunRegistryRepository()

    result = ReasoningSession(
        reasoning_run_registry_repository=reasoning_run_registry_repository,
    ).run(goal, observations)

    entries = reasoning_run_registry_repository.list()

    assert len(entries) == 1
    assert entries[0].run_id == result.run.id
    assert entries[0].started_at == result.run.started_at


def test_reasoning_session_registers_runs_in_execution_order() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_registry_repository = InMemoryReasoningRunRegistryRepository()
    session = ReasoningSession(
        reasoning_run_registry_repository=reasoning_run_registry_repository,
    )

    first_result = session.run(goal, observations)
    second_result = session.run(goal, observations)

    entries = reasoning_run_registry_repository.list()

    assert tuple(entry.run_id for entry in entries) == (
        first_result.run.id,
        second_result.run.id,
    )


def test_duplicate_registry_run_id_propagates_failure() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    reasoning_run_registry_repository = InMemoryReasoningRunRegistryRepository()

    with patch(
        "application.reasoning_session.uuid4",
        return_value="fixed-run-id",
    ):
        ReasoningSession(
            reasoning_run_registry_repository=reasoning_run_registry_repository,
        ).run(goal, observations)

        with pytest.raises(ValueError, match="already registered"):
            ReasoningSession(
                reasoning_run_registry_repository=reasoning_run_registry_repository,
            ).run(goal, observations)


def test_reasoning_session_without_registry_is_unchanged() -> None:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0])

    result = ReasoningSession().run(goal, observations)

    assert result.situation.assessment == "Increasing operational stress detected"
    assert result.run.id
