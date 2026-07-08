import dataclasses

import pytest

from application.reasoning_session import ReasoningSession
from application.reasoning_trace import ReasoningTrace, TraceStep
from tests.builders import build_goal, build_observation_sequence

EXPECTED_STEP_NAMES = (
    "Observations Loaded",
    "Trend Detected",
    "Variation Detected",
    "Relationship Analysis",
    "Operational Context Built",
    "Expectations Evaluated",
    "Situation Assessed",
    "Decision Context Created",
    "Decision Planned",
    "Action Recorded",
    "Outcome Recorded",
)


def build_trace() -> ReasoningTrace:
    goal = build_goal()
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    return ReasoningSession().run(goal, observations).trace


def test_trace_contains_the_expected_number_of_steps() -> None:
    trace = build_trace()

    assert len(trace.steps) == len(EXPECTED_STEP_NAMES)


def test_trace_step_names_are_correct_and_ordered() -> None:
    trace = build_trace()

    assert tuple(step.name for step in trace.steps) == EXPECTED_STEP_NAMES


def test_trace_steps_have_concise_descriptions() -> None:
    trace = build_trace()

    for step in trace.steps:
        assert step.description
        assert step.description.endswith(".")


def test_trace_is_immutable() -> None:
    trace = build_trace()

    with pytest.raises(dataclasses.FrozenInstanceError):
        trace.steps = ()  # type: ignore[misc]


def test_trace_step_is_immutable() -> None:
    step = TraceStep(name="Observations Loaded", description="Loaded.")

    with pytest.raises(dataclasses.FrozenInstanceError):
        step.name = "Changed"  # type: ignore[misc]
