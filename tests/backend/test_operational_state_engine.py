from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.application.operational_state_engine import OperationalStateEngine
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.priority import Priority


def test_operational_state_engine_is_deterministic_and_bounded() -> None:
    engine = OperationalStateEngine()
    now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    asset_id = "asset-engine"

    observations = [
        Observation(
            id="obs-1",
            asset_id=asset_id,
            timestamp=now,
            measurement_type=MeasurementType(name="temperature"),
            value=10.0,
            unit="celsius",
        ),
        Observation(
            id="obs-2",
            asset_id=asset_id,
            timestamp=now + timedelta(minutes=1),
            measurement_type=MeasurementType(name="temperature"),
            value=20.0,
            unit="celsius",
        ),
        Observation(
            id="obs-3",
            asset_id=asset_id,
            timestamp=now + timedelta(minutes=2),
            measurement_type=MeasurementType(name="temperature"),
            value=30.0,
            unit="celsius",
        ),
    ]

    plan = DecisionPlan(
        id="plan-1",
        context_id="ctx-1",
        created_at=now,
        priority=Priority.HIGH,
        recommendation="Investigate operational conditions",
        justification="Operational assessment indicates increasing stress.",
    )

    state = engine.compute(
        asset_id=asset_id,
        last_updated=now,
        assessment="Increasing operational stress detected",
        observations=observations,
        decision_plan=plan,
        structured_assessment=None,
    )

    assert state.asset_id == asset_id
    assert 0 <= state.health_score <= 100
    assert state.health_status in {"NORMAL", "WARNING", "CRITICAL"}
    assert state.risk_level in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= state.confidence <= 100
    assert state.primary_driver
    assert state.recommended_action
    assert state.last_updated == now

