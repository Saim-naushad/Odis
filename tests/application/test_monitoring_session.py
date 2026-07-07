from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field

import pytest

from application.monitoring_session import MonitoringResult, MonitoringSession
from application.observation_pipeline import ObservationPipeline
from application.observation_source import ObservationSource
from application.reasoning_session import ReasoningResult, ReasoningSession
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from tests.builders import build_goal, build_observation_sequence


@dataclass
class FakeObservationSource:
    observations: tuple[Observation, ...] = ()
    read_count: int = field(default=0, init=False)

    def read(self) -> tuple[Observation, ...]:
        self.read_count += 1
        return self.observations


@dataclass
class FakePipeline:
    results: tuple[ReasoningResult, ...]
    calls: list[tuple[OperationalGoal, ObservationSource]] = field(
        default_factory=list, init=False
    )

    def process(
        self, goal: OperationalGoal, source: ObservationSource
    ) -> ReasoningResult:
        self.calls.append((goal, source))
        return self.results[len(self.calls) - 1]


def _build_result_for(observations: tuple[Observation, ...]) -> ReasoningResult:
    goal = build_goal()
    return ReasoningSession().run(goal, observations)


def test_process_zero_sources() -> None:
    goal = build_goal()
    session = MonitoringSession()

    result = session.process(goal, ())

    assert result == MonitoringResult(runs=())


def test_process_one_source() -> None:
    goal = build_goal()
    observations = tuple(build_observation_sequence([32.0, 36.5, 41.0]))
    source = FakeObservationSource(observations=observations)
    pipeline = ObservationPipeline(session=ReasoningSession())
    session = MonitoringSession(pipeline=pipeline)

    result = session.process(goal, (source,))

    assert len(result.runs) == 1
    assert source.read_count == 1


def test_process_multiple_sources_preserves_order_and_calls_pipeline_once() -> None:
    goal = build_goal()
    first_observations = tuple(build_observation_sequence([32.0, 36.5, 41.0]))
    second_observations = tuple(build_observation_sequence([10.0, 20.0, 30.0]))
    sources = (
        FakeObservationSource(observations=first_observations),
        FakeObservationSource(observations=second_observations),
    )

    expected_first = _build_result_for(first_observations)
    expected_second = _build_result_for(second_observations)
    fake_pipeline = FakePipeline(results=(expected_first, expected_second))
    session = MonitoringSession(pipeline=fake_pipeline)  # type: ignore[arg-type]

    result = session.process(goal, sources)

    assert result.runs == (expected_first, expected_second)
    assert len(fake_pipeline.calls) == 2
    assert fake_pipeline.calls[0][1] is sources[0]
    assert fake_pipeline.calls[1][1] is sources[1]


def test_monitoring_result_is_immutable() -> None:
    observations = tuple(build_observation_sequence([1.0, 2.0]))
    single_run = ReasoningSession().run(build_goal(), observations)
    result = MonitoringResult(runs=(single_run,))

    with pytest.raises(FrozenInstanceError):
        result.runs = ()  # type: ignore[misc]

    with pytest.raises(TypeError):
        result.runs[0] = single_run  # type: ignore[index]
