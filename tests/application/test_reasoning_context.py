import pytest

from application.operational_profile import OperationalProfile
from application.reasoning.context import (
    ReasoningArtifacts,
    ReasoningContext,
    ReasoningMetadata,
    primary_measurement_observations,
)
from domain.reasoning.evidence import Evidence, EvidenceRole, EvidenceSourceSignal
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_goal, build_observation, build_observation_sequence


def test_reasoning_context_groups_outputs_in_artifacts() -> None:
    goal = build_goal()
    observations = build_observation_sequence([10.0, 12.0])

    context = ReasoningContext(
        goal=goal,
        observations=observations,
        profile=OperationalProfile.default(),
        artifacts=ReasoningArtifacts(),
        metadata=ReasoningMetadata(run_id="run-1"),
    )

    assert context.goal is goal
    assert context.observations == observations
    assert context.artifacts.signals is None
    assert context.metadata.run_id == "run-1"


def test_reasoning_context_with_artifacts_returns_new_instance() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([1.0, 2.0]),
        profile=OperationalProfile.default(),
    )
    evidence = (
        Evidence(
            id=EvidenceSourceSignal.LATEST_READING,
            description="Latest reading",
            source_signal=EvidenceSourceSignal.LATEST_READING,
            measurement_type="temperature",
            observed_value="12.0 celsius",
            role=EvidenceRole.PRIMARY_SUPPORT,
            weight=0.35,
        ),
    )

    updated = context.with_artifacts(evidence=evidence)

    assert updated is not context
    assert updated.artifacts.evidence == evidence
    assert context.artifacts.evidence == ()


def test_primary_measurement_observations_filters_by_first_type() -> None:
    temperature = build_observation(id="t1", value=10.0)
    pressure = build_observation(
        id="p1",
        measurement_type=MeasurementType(name="pressure"),
        value=5.0,
    )

    primary = primary_measurement_observations((temperature, pressure))

    assert primary == (temperature,)


def test_reasoning_context_requires_observations_for_downstream_stages() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=(),
        profile=OperationalProfile.default(),
    )

    with pytest.raises(ValueError, match="at least two observations"):
        from application.reasoning.signal_extraction_stage import SignalExtractionStage

        SignalExtractionStage().run(context)
