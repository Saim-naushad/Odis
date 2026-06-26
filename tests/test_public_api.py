import odis


def test_public_api_exports_expected_symbols() -> None:
    expected = (
        "Action",
        "Asset",
        "DecisionContext",
        "DecisionPlanner",
        "DecisionPlan",
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
