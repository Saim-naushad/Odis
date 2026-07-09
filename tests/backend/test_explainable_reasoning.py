from datetime import UTC, datetime

from backend.app.application.explainable_reasoning import build_explainable_decision
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.priority import Priority


def _obs(
    *,
    id: str,
    value: float,
    timestamp: datetime,
    asset_id: str = "asset-1",
    measurement_type: str = "temperature",
    unit: str = "celsius",
) -> Observation:
    return Observation(
        id=id,
        asset_id=asset_id,
        timestamp=timestamp,
        measurement_type=MeasurementType(measurement_type),
        value=value,
        unit=unit,
    )


def test_confidence_increases_with_more_supporting_observations() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    plan = DecisionPlan(
        id="plan-1",
        context_id="ctx-1",
        created_at=base_time,
        priority=Priority.HIGH,
        recommendation="Investigate operational conditions",
        justification="Operational assessment indicates increasing stress.",
    )

    decision_two = build_explainable_decision(
        assessment="Increasing trend detected",
        observations=[
            _obs(id="o1", value=30.0, timestamp=base_time),
            _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
        ],
        decision_plan=plan,
        structured_assessment=None,
    )
    decision_three = build_explainable_decision(
        assessment="Increasing trend detected",
        observations=[
            _obs(id="o1", value=30.0, timestamp=base_time),
            _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
            _obs(id="o3", value=50.0, timestamp=base_time.replace(minute=2)),
        ],
        decision_plan=plan,
        structured_assessment=None,
    )

    assert decision_three.confidence.value >= decision_two.confidence.value


def test_evidence_is_deterministic_and_includes_recent_delta_when_available() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    plan = DecisionPlan(
        id="plan-2",
        context_id="ctx-2",
        created_at=base_time,
        priority=Priority.LOW,
        recommendation="Continue monitoring",
        justification="Operational conditions remain stable.",
    )
    decision = build_explainable_decision(
        assessment="Stable conditions",
        observations=[
            _obs(id="o1", value=10.0, timestamp=base_time),
            _obs(id="o2", value=12.0, timestamp=base_time.replace(minute=1)),
        ],
        decision_plan=plan,
        structured_assessment=None,
    )

    evidence_ids = [item.id for item in decision.evidence]
    assert evidence_ids == [
        "latest_reading",
        "recent_delta",
        "sample_support",
        "planner_alignment",
    ]


def test_alternatives_are_deterministic_and_limited() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    plan = DecisionPlan(
        id="plan-3",
        context_id="ctx-3",
        created_at=base_time,
        priority=Priority.HIGH,
        recommendation="Investigate operational conditions",
        justification="Operational assessment indicates increasing stress.",
    )
    decision = build_explainable_decision(
        assessment="Increasing trend detected",
        observations=[
            _obs(id="o1", value=30.0, timestamp=base_time),
            _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
        ],
        decision_plan=plan,
        structured_assessment=None,
    )

    assert 1 <= len(decision.alternative_hypotheses) <= 2
    assert all(0 <= item.confidence <= 100 for item in decision.alternative_hypotheses)

