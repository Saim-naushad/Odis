from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from application.monitoring_timeline import MonitoringTimeline
from application.reasoning_session import ReasoningResult, ReasoningSession
from application.timeline_trend_analysis import TimelineTrendAnalyzer
from domain.value_objects.priority import Priority
from tests.builders import build_goal, build_observation_sequence


def _run_result(*, id_prefix: str) -> ReasoningResult:
    session = ReasoningSession()
    goal = build_goal()
    observations = build_observation_sequence(
        [10.0, 20.0, 30.0, 40.0, 50.0],
        id_prefix=id_prefix,
    )
    return session.run(goal, observations)


def _with_priority(result: ReasoningResult, priority: Priority) -> ReasoningResult:
    updated_plan = replace(result.plan, id=str(uuid4()), priority=priority)
    return replace(result, plan=updated_plan)


def test_empty_timeline_is_stable() -> None:
    analyzer = TimelineTrendAnalyzer()
    timeline = MonitoringTimeline()

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend == "stable"


def test_single_run_is_stable() -> None:
    analyzer = TimelineTrendAnalyzer()
    timeline = MonitoringTimeline().append(_run_result(id_prefix="one"))

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend == "stable"


def test_improving_when_priority_decreases() -> None:
    analyzer = TimelineTrendAnalyzer()
    first = _with_priority(_run_result(id_prefix="first"), Priority.HIGH)
    last = _with_priority(_run_result(id_prefix="last"), Priority.LOW)
    timeline = MonitoringTimeline(runs=(first, last))

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend == "improving"


def test_worsening_when_priority_increases() -> None:
    analyzer = TimelineTrendAnalyzer()
    first = _with_priority(_run_result(id_prefix="first"), Priority.LOW)
    last = _with_priority(_run_result(id_prefix="last"), Priority.CRITICAL)
    timeline = MonitoringTimeline(runs=(first, last))

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend == "worsening"


def test_stable_when_priority_unchanged() -> None:
    analyzer = TimelineTrendAnalyzer()
    first = _with_priority(_run_result(id_prefix="first"), Priority.MEDIUM)
    last = _with_priority(_run_result(id_prefix="last"), Priority.MEDIUM)
    timeline = MonitoringTimeline(runs=(first, last))

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend == "stable"


def test_analysis_is_immutable() -> None:
    analyzer = TimelineTrendAnalyzer()
    timeline = MonitoringTimeline().append(_run_result(id_prefix="one"))
    analysis = analyzer.analyze(timeline)

    with pytest.raises(FrozenInstanceError):
        analysis.priority_trend = "worsening"  # type: ignore[misc]


def test_priority_trend_is_one_of_allowed_values() -> None:
    analyzer = TimelineTrendAnalyzer()
    first = _with_priority(_run_result(id_prefix="first"), Priority.MEDIUM)
    last = _with_priority(_run_result(id_prefix="last"), Priority.CRITICAL)
    timeline = MonitoringTimeline(runs=(first, last))

    analysis = analyzer.analyze(timeline)

    assert analysis.priority_trend in {"improving", "stable", "worsening"}


def test_timeline_append_returns_new_instance() -> None:
    timeline = MonitoringTimeline()
    result = _run_result(id_prefix="one")

    updated = timeline.append(result)

    assert timeline.count() == 0
    assert updated.count() == 1

