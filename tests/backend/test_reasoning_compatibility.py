from datetime import UTC, datetime

from backend.app.application.reasoning_compatibility import (
    build_explainable_decision,
    build_reasoning_context_through_explanation,
    to_backend_evidence,
    to_confidence_score,
)
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_GOAL
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.priority import Priority


def _obs(
    *,
    id: str,
    value: float,
    timestamp: datetime,
) -> Observation:
    return Observation(
        id=id,
        asset_id="asset-1",
        timestamp=timestamp,
        measurement_type=MeasurementType("temperature"),
        value=value,
        unit="celsius",
    )


def test_build_reasoning_context_through_explanation_populates_v2_artifacts() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    observations = [
        _obs(id="o1", value=30.0, timestamp=base_time),
        _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
        _obs(id="o3", value=50.0, timestamp=base_time.replace(minute=2)),
    ]

    context = build_reasoning_context_through_explanation(
        goal=DEFAULT_OPERATIONAL_GOAL,
        observations=observations,
    )
    artifacts = context.artifacts

    assert artifacts.assessment_summary is not None
    assert artifacts.confidence is not None
    assert artifacts.explanation is not None
    assert artifacts.hypotheses
    assert artifacts.evidence


def test_canonical_to_backend_evidence_mapping() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    context = build_reasoning_context_through_explanation(
        goal=DEFAULT_OPERATIONAL_GOAL,
        observations=[
            _obs(id="o1", value=30.0, timestamp=base_time),
            _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
        ],
    )
    canonical = context.artifacts.evidence[0]
    backend = to_backend_evidence(canonical)

    assert backend.id == canonical.id
    assert backend.contribution_weight == canonical.weight


def test_assessment_confidence_differs_from_legacy_plan_severity_confidence() -> None:
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    observations = [
        _obs(id="o1", value=30.0, timestamp=base_time),
        _obs(id="o2", value=45.0, timestamp=base_time.replace(minute=1)),
        _obs(id="o3", value=50.0, timestamp=base_time.replace(minute=2)),
    ]
    plan = DecisionPlan(
        id="plan-1",
        context_id="ctx-1",
        created_at=base_time,
        priority=Priority.HIGH,
        recommendation="Investigate operational conditions",
        justification="Operational assessment indicates increasing stress.",
    )

    context = build_reasoning_context_through_explanation(
        goal=DEFAULT_OPERATIONAL_GOAL,
        observations=observations,
    )
    legacy = build_explainable_decision(
        assessment="Increasing trend detected",
        observations=observations,
        decision_plan=plan,
        structured_assessment=context.artifacts.structured_assessment,
    )
    assessment_confidence = to_confidence_score(context.artifacts.confidence)  # type: ignore[arg-type]

    assert "Severity" in legacy.confidence.rationale
    assert "Severity" not in assessment_confidence.rationale
