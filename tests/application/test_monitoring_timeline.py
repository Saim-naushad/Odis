from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from application.monitoring_timeline import MonitoringTimeline
from application.reasoning_session import ReasoningResult, ReasoningSession
from tests.builders import build_goal, build_observation_sequence


def _build_run(values: list[float]) -> ReasoningResult:
    observations = tuple(build_observation_sequence(values))
    return ReasoningSession().run(build_goal(), observations)


def test_empty_timeline() -> None:
    timeline = MonitoringTimeline()

    assert timeline.runs == ()
    assert timeline.latest() is None
    assert timeline.previous() is None
    assert timeline.count() == 0


def test_append_returns_new_timeline_without_mutation() -> None:
    first = _build_run([1.0, 2.0])
    timeline = MonitoringTimeline()

    updated = timeline.append(first)

    assert timeline.runs == ()
    assert updated.runs == (first,)
    assert updated is not timeline


def test_latest_and_previous() -> None:
    first = _build_run([1.0, 2.0])
    second = _build_run([10.0, 20.0])
    timeline = MonitoringTimeline().append(first).append(second)

    assert timeline.latest() == second
    assert timeline.previous() == first


def test_ordering_preserved() -> None:
    first = _build_run([1.0, 2.0])
    second = _build_run([10.0, 20.0])
    third = _build_run([100.0, 200.0])

    timeline = MonitoringTimeline()
    timeline = timeline.append(first)
    timeline = timeline.append(second)
    timeline = timeline.append(third)

    assert timeline.runs == (first, second, third)


def test_timeline_is_immutable() -> None:
    run = _build_run([1.0, 2.0])
    timeline = MonitoringTimeline(runs=(run,))

    with pytest.raises(FrozenInstanceError):
        timeline.runs = ()  # type: ignore[misc]

    with pytest.raises(TypeError):
        timeline.runs[0] = run  # type: ignore[index]
