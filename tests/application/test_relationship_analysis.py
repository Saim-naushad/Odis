from datetime import UTC, datetime

from application.contradiction_detector import (
    ContradictionDetector,
    OperationalContradiction,
)
from application.correlation_detector import CorrelationDetector, MeasurementCorrelation
from application.observation_group import ObservationGroup
from application.relationship_analysis import RelationshipAnalyzer
from domain.value_objects.measurement_type import MeasurementType
from tests.builders import build_observation, build_observation_sequence


def test_no_relationships_returns_empty_analysis() -> None:
    temperature = MeasurementType(name="temperature")
    temp_obs = build_observation_sequence([10, 20], measurement_type=temperature)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs)

    analysis = RelationshipAnalyzer().analyze(group)

    assert analysis.correlations == ()
    assert analysis.contradictions == ()


def test_correlations_only() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 20, 10], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    analysis = RelationshipAnalyzer().analyze(group)

    assert len(analysis.correlations) == 1
    assert analysis.contradictions == ()


def test_contradictions_only() -> None:
    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    temp_obs = build_observation_sequence([10, 20, 30], measurement_type=temperature)
    pressure_obs = build_observation_sequence([30, 40, 50], measurement_type=pressure)
    group = ObservationGroup(asset_id="asset-1", observations=temp_obs + pressure_obs)

    analysis = RelationshipAnalyzer().analyze(group)

    assert analysis.correlations == ()
    assert len(analysis.contradictions) == 1


class _FakeCorrelationDetector(CorrelationDetector):
    def __init__(self, result: tuple[MeasurementCorrelation, ...]) -> None:
        super().__init__()
        self._result = result
        self.called_with: ObservationGroup | None = None

    def detect(self, group: ObservationGroup) -> tuple[MeasurementCorrelation, ...]:
        self.called_with = group
        return self._result


class _FakeContradictionDetector(ContradictionDetector):
    def __init__(self, result: tuple[OperationalContradiction, ...]) -> None:
        super().__init__()
        self._result = result
        self.called_with: ObservationGroup | None = None

    def detect(self, group: ObservationGroup) -> tuple[OperationalContradiction, ...]:
        self.called_with = group
        return self._result


def test_both_relationship_types_are_aggregated() -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    group = ObservationGroup(
        asset_id="asset-1",
        observations=(
            build_observation(id="o-1", timestamp=base),
            build_observation(id="o-2", timestamp=base.replace(minute=1)),
        ),
    )

    temperature = MeasurementType(name="temperature")
    pressure = MeasurementType(name="pressure")

    fake_correlations = (
        MeasurementCorrelation(
            measurement_a=temperature,
            measurement_b=pressure,
            relationship="fake-correlation",
        ),
    )
    fake_contradictions = (
        OperationalContradiction(description="fake-contradiction"),
    )

    correlation_detector = _FakeCorrelationDetector(fake_correlations)
    contradiction_detector = _FakeContradictionDetector(fake_contradictions)

    analysis = RelationshipAnalyzer(
        correlation_detector=correlation_detector,
        contradiction_detector=contradiction_detector,
    ).analyze(group)

    assert analysis.correlations == fake_correlations
    assert analysis.contradictions == fake_contradictions


def test_injected_detectors_are_used_instead_of_defaults() -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    group = ObservationGroup(
        asset_id="asset-1",
        observations=(
            build_observation(id="o-1", timestamp=base),
            build_observation(id="o-2", timestamp=base.replace(minute=1)),
        ),
    )

    correlation_detector = _FakeCorrelationDetector(())
    contradiction_detector = _FakeContradictionDetector(())

    RelationshipAnalyzer(
        correlation_detector=correlation_detector,
        contradiction_detector=contradiction_detector,
    ).analyze(group)

    assert correlation_detector.called_with is group
    assert contradiction_detector.called_with is group

