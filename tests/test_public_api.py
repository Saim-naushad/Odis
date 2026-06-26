from datetime import UTC, datetime

import odis


def test_public_api_exports_expected_symbols() -> None:
    expected = (
        "Action",
        "Asset",
        "DecisionContext",
        "DecisionPlanner",
        "DecisionPlan",
        "Location",
        "MeasurementType",
        "Observation",
        "OperationalGoal",
        "OperationalSituation",
        "OperationalSituationAssessor",
        "Outcome",
        "Priority",
        "ReasoningResult",
        "ReasoningRun",
        "ReasoningSession",
        "TrendDetector",
        "TrendDirection",
        "VariationDetector",
        "VariationLevel",
        "record_action",
        "record_outcome",
    )

    assert set(odis.__all__) == set(expected)
    for name in expected:
        assert hasattr(odis, name)


def test_exported_domain_entities_are_constructible_from_public_api() -> None:
    location = odis.Location(identifier="site-1")
    asset = odis.Asset(
        id="asset-1",
        name="Pump P-07",
        type="centrifugal_pump",
        location=location,
    )
    goal = odis.OperationalGoal(
        id="goal-1",
        description="Maintain stable process conditions",
    )
    measurement_type = odis.MeasurementType(name="pressure")
    observation = odis.Observation(
        id="obs-1",
        asset_id=asset.id,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        measurement_type=measurement_type,
        value=120.0,
        unit="kPa",
    )
    situation = odis.OperationalSituation(
        id="situation-1",
        goal_id=goal.id,
        observation_ids=(observation.id,),
        assessment="Operational conditions stable",
    )
    context = odis.DecisionContext(
        id="context-1",
        goal_id=goal.id,
        situation_id=situation.id,
        assessment=situation.assessment,
        created_at=datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
    )
    plan = odis.DecisionPlan(
        id="plan-1",
        context_id=context.id,
        created_at=datetime(2026, 1, 1, 12, 10, tzinfo=UTC),
        priority=odis.Priority.LOW,
        recommendation="Continue monitoring",
        justification="Operational conditions remain stable.",
    )
    action = odis.record_action(plan)
    outcome = odis.record_outcome(action)

    assert action.plan_id == plan.id
    assert outcome.action_id == action.id
